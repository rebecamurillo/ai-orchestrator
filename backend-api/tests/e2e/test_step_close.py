"""Closing a conversation step against the running stack (initiative
orchestrator-initiative-steps, epic 5, SPEC CAP-1..CAP-3).

The unit suite proves each rule over fakes. What only the running stack settles: a real turn
dispatched on the interactive queue hands the harness the row's close clause with its own
attempt id; the attestation the turn leaves in its worktree is judged after the turn's commit
by the real walker, and only the one naming that very turn, on a turn that ended `done` with
no later message pending, sends `step_close`; the resumed execute runs the AD-17 close check
over the session's real git diff and routes the step file the turn committed.

The `fake` harness cannot write an attempt id it does not know, so the test writes the
attestation into the turn's worktree itself, through the backend container, while the turn's
process sleeps: after the dispatcher's turn-start removal and before the turn ends. Every
template is a fresh name this module owns and every repository a fresh bare origin whose
`.fake-harness/` scripts the turns (hard rule 6). Every Run is cancelled when its test ends.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import yaml

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.infrastructure.db import (
    SQLAlchemyRunRepository,
    create_engine_from,
    create_session_factory,
)
from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import DOCKER_TIMEOUT_SECONDS, REPO_ROOT
from tests.e2e.test_conversation_stop import (
    FIRST_TURN,
    HTTP_CREATED,
    HTTP_OK,
    TIMEOUT_SECONDS,
    detail_of,
    parked_on,
    row,
    session_of,
    signal,
    talking_origin,
    turns_of,
    wait_for,
)
from tests.e2e.test_run_creation import (
    RUNS,
    TEMPLATES,
    clone_check,
    create_project,
    create_repository,
    project_id_of,
    run_payload,
)

CLOSE_FILE = ".orchestrator/session/close"
PROMPT_SUFFIX = ".prompt"
STEP_FILE = "docs/product.md"
FOLDER = "initiatives"
SLUG = "demo"
FOLDER_ANCHOR = f"{FOLDER}/{SLUG}/epics.yaml"
OUTSIDE_ANCHOR = "backend-api/AGENTS.md"
#: Long enough for the test to find the turn's prompt and write the attestation.
TURN_SECONDS = 8

TEMPLATE = """name: @NAME@
version: 1
description: e2e epic 5 closing a step
type: interactive
inputs:
  project:          { type: project,    required: true }
  repository:       { type: repository, required: true }
  base_branch:      { type: string,     required: true }
  first_turn:       { type: string,     required: false }
  initiative_folder: { type: string,    required: false }
  slug:             { type: string,     required: false }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: '{{base_branch}}', branch: 'e2e/close-@NAME@' }
    gate: deterministic
@ROWS@"""

ROW = """  - id: @STEP@
    uses: conversation
    role: plan
    gate: human
    with: { step: @STEP@, skill: skills/talk/SKILL.md, persona: personas/analyst.md }
    expect:
      files: ["docs/@STEP@.md"]
      success: [done]
      blocked: [blocked]
    writes: ["docs/@STEP@.md", "epics.yaml"]
    prompts:
      open: "Open @STEP@."
      close: "Close @STEP@ as {attempt_id}."
"""

WRITE_CLOSE = """
set -e
mkdir -p "$1/.orchestrator/session"
printf '%s' "$2" > "$1/.orchestrator/session/close"
"""


def template_text(name: str) -> str:
    rows = "".join(ROW.replace("@STEP@", step) for step in ("product", "ux"))
    return TEMPLATE.replace("@ROWS@", rows).replace("@NAME@", name)


def scenario(*, seconds: float = 0, exit_code: int = 0, files: dict[str, str] | None = None) -> str:
    """One turn of the fake harness, as the YAML document it reads."""
    document: dict[str, Any] = {"exit_code": exit_code}
    if seconds:
        document["sleep_seconds"] = seconds
    if files:
        document["files"] = [{"path": path, "content": text} for path, text in files.items()]
    return yaml.safe_dump(document)


def step_file(status: str | None) -> dict[str, str]:
    body = "# Product\n" if status is None else f"---\nstatus: {status}\n---\n# Product\n"
    return {STEP_FILE: body}


QUICK = scenario()


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture(scope="module")
def sessions(settings: Settings) -> Iterator[Any]:
    engine = create_engine_from(settings)
    try:
        yield create_session_factory(engine)
    finally:
        engine.dispose()


def in_stack(script: str, *arguments: str) -> subprocess.CompletedProcess[str] | None:
    """`script` run where the backend sees its worktrees: the container, else the host.

    `None` when neither route answers; otherwise the first route's completed process.
    """
    for prefix in (("docker", "compose", "exec", "-T", "backend-api"), ()):
        try:
            return subprocess.run(  # fixed argv, no shell
                [*prefix, "sh", "-c", script, "sh", *arguments],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=DOCKER_TIMEOUT_SECONDS,
            )
        except OSError, subprocess.TimeoutExpired:
            continue
    return None


def worktree_of(sessions: Any, run_id: str) -> str:
    with sessions() as session:
        run = SQLAlchemyRunRepository(session).get(UUID(run_id))
    assert run is not None and run.worktree_path, run
    return run.worktree_path


def prompt_of(sessions: Any, run_id: str, path: str, n: int) -> tuple[Attempt, str]:
    """The n-th turn of `path` and the prompt its harness received, once it has one."""

    def read() -> tuple[Attempt | None, str | None]:
        turns = turns_of(sessions, run_id, path)
        turn = turns[n - 1] if len(turns) >= n else None
        if turn is None or not turn.log_path:
            return turn, None
        done = in_stack('cat "$1"', f"{turn.log_path}{PROMPT_SUFFIX}")
        return turn, done.stdout if done is not None and done.returncode == 0 else None

    turn, prompt = wait_for(read, lambda found: found[1] is not None, f"turn {n}'s prompt")
    assert turn is not None and prompt is not None
    return turn, prompt


def running_turn(sessions: Any, run_id: str, path: str, n: int) -> Attempt:
    """The n-th turn of `path` once its harness runs. A turn's `log_path`, which `prompt_of`
    waits for, is stored only when the turn ends: too late to attest during it."""

    def read() -> Attempt | None:
        turns = turns_of(sessions, run_id, path)
        return turns[n - 1] if len(turns) >= n else None

    turn = wait_for(
        read, lambda found: found is not None and found.status == "running", f"turn {n} running"
    )
    assert turn is not None
    return turn


def attest(sessions: Any, run_id: str, text: str) -> None:
    done = in_stack(WRITE_CLOSE, worktree_of(sessions, run_id), text)
    assert done is not None and done.returncode == 0, done


def close_file_exists(sessions: Any, run_id: str) -> bool:
    done = in_stack('test -e "$1/$2"', worktree_of(sessions, run_id), CLOSE_FILE)
    assert done is not None
    return done.returncode == 0


def records(detail: dict[str, Any], event: str) -> list[tuple[str, str]]:
    return [(e["actor"], e["text"]) for e in detail["gate_record"] if e["event"] == event]


def recorded(api: httpx.Client, run_id: str, event: str) -> dict[str, Any]:
    return wait_for(
        lambda: detail_of(api, run_id),
        lambda detail: bool(records(detail, event)),
        f"a {event} gate record",
    )


def turns_settled(api: httpx.Client, run_id: str, count: int) -> dict[str, Any]:
    """The session once `count` turns exist and none is running."""
    return wait_for(
        lambda: session_of(api, run_id),
        lambda view: len(view["turns"]) >= count and not view["turn_running"],
        f"{count} turns ending",
    )


def barrier(api: httpx.Client, run_id: str, count: int) -> None:
    """Post one more message and wait for its turn to end, so every earlier turn's end —
    the attestation check included — has run: session turns run one after another."""
    posted = api.post(f"{RUNS}/{run_id}/session/messages", json={"text": "one more thing"})
    assert posted.is_success, posted.text
    turns_settled(api, run_id, count + 1)


@pytest.fixture
def start_run(api: httpx.Client, settings: Settings) -> Iterator[Callable[..., str]]:
    """`start_run(first, rest=QUICK, **inputs) -> run_id` on a fresh origin and template."""
    started: list[str] = []

    def start(first: str, rest: str = QUICK, **inputs: str) -> str:
        repository_id = create_repository(
            api, create_project(api), talking_origin(settings, first, rest)
        )
        clone_check(api, repository_id)
        name = f"e2e-close-{uuid4().hex}"
        stored = api.post(f"{TEMPLATES}/{name}/versions", json={"yaml": template_text(name)})
        assert stored.status_code == HTTP_CREATED, stored.text
        payload = run_payload(
            name,
            repository_id,
            project_id=project_id_of(api, repository_id),
            harness="fake",
            inputs={"first_turn": FIRST_TURN, **inputs},
        )
        response = api.post(RUNS, json=payload)
        assert response.status_code == HTTP_CREATED, response.text
        run_id = str(response.json()["run"]["id"])
        started.append(run_id)
        return run_id

    yield start
    for run_id in started:
        signal(api, run_id, "cancel", confirm=True)


# ── CAP-1: the attestation closes a step only for the turn it answers ────────────────────


def test_a_turn_attesting_its_own_id_closes_the_step_and_the_next_row_runs(
    api: httpx.Client, sessions: Any, start_run: Callable[..., str]
) -> None:
    run_id = start_run(scenario(seconds=TURN_SECONDS, files=step_file("done")))
    stop = parked_on(api, run_id, "product")["run"]["park_seq"]
    turn = running_turn(sessions, run_id, "product", 1)

    attest(sessions, run_id, str(turn.id))
    detail = parked_on(api, run_id, "ux")

    _, prompt = prompt_of(sessions, run_id, "product", 1)
    assert f"{FIRST_TURN}\n\nClose product as {turn.id}." in prompt
    assert turns_of(sessions, run_id, "product")[0].message == FIRST_TURN
    assert row(detail, "product")["status"] == "done"
    assert detail["run"]["park_seq"] > stop
    assert records(detail, "step_close") == [("machine", "step closed")]
    assert records(detail, "close_discarded") == []
    assert not close_file_exists(sessions, run_id)


def test_an_attestation_naming_another_attempt_is_discarded_and_sends_nothing(
    api: httpx.Client, sessions: Any, start_run: Callable[..., str]
) -> None:
    run_id = start_run(scenario(seconds=TURN_SECONDS, files=step_file("done")))
    stop = parked_on(api, run_id, "product")["run"]["park_seq"]
    running_turn(sessions, run_id, "product", 1)
    foreign = str(uuid4())

    attest(sessions, run_id, foreign)
    detail = recorded(api, run_id, "close_discarded")

    discarded = [("machine", f"close discarded: attempt {foreign}")]
    assert records(detail, "close_discarded") == discarded
    assert records(detail, "step_close") == []
    assert row(detail, "product")["status"] == "checkpoint"
    assert detail["run"]["park_seq"] == stop
    assert not close_file_exists(sessions, run_id)


def test_an_attestation_with_a_later_message_pending_is_deferred(
    api: httpx.Client, sessions: Any, start_run: Callable[..., str]
) -> None:
    run_id = start_run(scenario(seconds=TURN_SECONDS, files=step_file("done")))
    stop = parked_on(api, run_id, "product")["run"]["park_seq"]
    turn = running_turn(sessions, run_id, "product", 1)
    queued = api.post(f"{RUNS}/{run_id}/session/messages", json={"text": "wait, one more"})

    attest(sessions, run_id, str(turn.id))
    recorded(api, run_id, "close_discarded")
    barrier(api, run_id, 2)
    detail = detail_of(api, run_id)

    assert queued.is_success, queued.text
    assert records(detail, "close_discarded") == [("machine", "close deferred: later message")]
    assert records(detail, "step_close") == []
    assert row(detail, "product")["status"] == "checkpoint"
    assert detail["run"]["park_seq"] == stop


def test_an_attestation_on_a_failed_turn_is_discarded(
    api: httpx.Client, sessions: Any, start_run: Callable[..., str]
) -> None:
    run_id = start_run(scenario(seconds=TURN_SECONDS, exit_code=1, files=step_file("done")))
    stop = parked_on(api, run_id, "product")["run"]["park_seq"]
    turn = running_turn(sessions, run_id, "product", 1)

    attest(sessions, run_id, str(turn.id))
    detail = recorded(api, run_id, "close_discarded")

    assert turns_of(sessions, run_id, "product")[0].status == "error"
    assert records(detail, "close_discarded") == [("machine", "close discarded: turn failed")]
    assert records(detail, "step_close") == []
    assert detail["run"]["park_seq"] == stop


def test_a_done_step_file_without_an_attestation_closes_nothing(
    api: httpx.Client, start_run: Callable[..., str]
) -> None:
    run_id = start_run(scenario(files=step_file("done")))
    stop = parked_on(api, run_id, "product")["run"]["park_seq"]
    turns_settled(api, run_id, 1)

    barrier(api, run_id, 1)
    detail = detail_of(api, run_id)

    assert records(detail, "step_close") == []
    assert records(detail, "close_discarded") == []
    assert row(detail, "product")["status"] == "checkpoint"
    assert detail["run"]["park_seq"] == stop


def test_an_attestation_left_by_an_earlier_turn_is_removed_when_the_next_turn_starts(
    api: httpx.Client, sessions: Any, start_run: Callable[..., str]
) -> None:
    run_id = start_run(QUICK)
    stop = parked_on(api, run_id, "product")["run"]["park_seq"]
    turns_settled(api, run_id, 1)
    barrier(api, run_id, 1)
    earlier = turns_of(sessions, run_id, "product")[0]

    attest(sessions, run_id, str(earlier.id))
    barrier(api, run_id, 2)
    barrier(api, run_id, 3)
    detail = detail_of(api, run_id)

    assert records(detail, "close_discarded") == []
    assert records(detail, "step_close") == []
    assert detail["run"]["park_seq"] == stop
    assert not close_file_exists(sessions, run_id)


# ── CAP-3: the resumed execute routes the step file ──────────────────────────────────────


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (
            "draft",
            "step not closed · docs/product.md has status draft,"
            " the done content is status done · the step stays open",
        ),
        (
            "blocked",
            "step not closed · docs/product.md has status blocked,"
            " the done content is status done · the step stays open",
        ),
        (
            None,
            "step not closed · docs/product.md is missing,"
            " the done content is status done · the step stays open",
        ),
    ],
)
def test_step_close_on_a_step_file_not_done_parks_the_conversation_again_saying_why(
    api: httpx.Client,
    sessions: Any,
    start_run: Callable[..., str],
    status: str | None,
    reason: str,
) -> None:
    run_id = start_run(scenario(files=step_file(status)) if status else QUICK)
    stop = parked_on(api, run_id, "product")["run"]["park_seq"]
    turns_settled(api, run_id, 1)

    closed = signal(api, run_id, "step_close", stop)
    detail = wait_for(
        lambda: parked_on(api, run_id, "product"),
        lambda detail: detail["run"]["park_seq"] > stop,
        "the row parking on a new stop",
    )

    assert closed.status_code == HTTP_OK, closed.text
    assert detail["alert"]["reason"] == reason
    assert detail["run"]["status"] == "needs_you"
    assert detail["run"]["senior_session"] is True
    assert session_of(api, run_id)["active"] is True
    assert len(turns_of(sessions, run_id, "product")) == 1
    assert row(detail, "ux")["status"] == "planned"


# ── CAP-2 with CAP-3: the initiative folder is the conversation's product ────────────────


def test_step_close_on_a_done_step_file_with_its_folder_anchor_ends_the_row(
    api: httpx.Client, start_run: Callable[..., str]
) -> None:
    files = {**step_file("done"), FOLDER_ANCHOR: "epics: []\n"}
    run_id = start_run(scenario(files=files), initiative_folder=FOLDER, slug=SLUG)
    stop = parked_on(api, run_id, "product")["run"]["park_seq"]
    turns_settled(api, run_id, 1)

    closed = signal(api, run_id, "step_close", stop)
    detail = parked_on(api, run_id, "ux")

    assert closed.status_code == HTTP_OK, closed.text
    assert row(detail, "product")["status"] == "done"
    assert [e for e in detail["gate_record"] if e["event"] == "protected_path"] == []


def test_an_anchor_outside_the_rows_writes_parks_protected_path_until_she_accepts_it(
    api: httpx.Client, start_run: Callable[..., str]
) -> None:
    files = {**step_file("done"), FOLDER_ANCHOR: "epics: []\n", OUTSIDE_ANCHOR: "# rules\n"}
    run_id = start_run(scenario(files=files), initiative_folder=FOLDER, slug=SLUG)
    stop = parked_on(api, run_id, "product")["run"]["park_seq"]
    turns_settled(api, run_id, 1)

    closed = signal(api, run_id, "step_close", stop)
    parked = wait_for(
        lambda: detail_of(api, run_id),
        lambda detail: (detail["alert"] or {}).get("park_kind") == "protected_path",
        "the row parking protected_path",
    )
    accepted = signal(api, run_id, "continue", parked["run"]["park_seq"], files=[OUTSIDE_ANCHOR])
    detail = parked_on(api, run_id, "ux")

    assert closed.status_code == HTTP_OK, closed.text
    assert [hit["path"] for hit in parked["alert"]["payload"]["hits"]] == [OUTSIDE_ANCHOR]
    assert OUTSIDE_ANCHOR in parked["alert"]["reason"]
    assert FOLDER_ANCHOR not in parked["alert"]["reason"]
    assert row(parked, "product")["status"] == "error"
    assert accepted.status_code == HTTP_OK, accepted.text
    assert row(detail, "product")["status"] == "done"
