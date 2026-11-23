"""The conversation stop against the running stack (initiative orchestrator-initiative-steps,
epic 4, SPEC CAP-1..CAP-6).

The unit suite proves each rule over fakes. What only the running stack settles: a
`conversation` row walked by the real engine parks the Run and opens its own session; the
first turn is dispatched on the real interactive queue to the scripted `fake` harness; a
message posted while that turn runs is queued; a forced skip or a cancel kills the running
turn and closes the queued ones; the walk reaches the next row only after the killed turn
ended; `step_close` resumes the row and a stale stop is refused; and a failed turn restarts
in the same harness session.

Every template is a fresh name this module owns, and every repository is a fresh bare origin
whose `.fake-harness/` scripts the turns (hard rule 6: no shipped template is read). A
conversation turn's prompt names no story, so the fake harness reads
`.fake-harness/attempt-{k}.yaml`, else `.fake-harness/default.yaml`. Every Run this module
starts is cancelled when its test ends.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.infrastructure.db import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyStepRunRepository,
    create_engine_from,
    create_session_factory,
)
from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import DOCKER_TIMEOUT_SECONDS, REPO_ROOT, manifest_stating
from tests.e2e.test_run_creation import (
    RUNS,
    TEMPLATES,
    clone_check,
    create_project,
    create_repository,
    project_id_of,
    run_payload,
)

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_ACCEPTED = 202
HTTP_CONFLICT = 409
TIMEOUT_SECONDS = 10.0
#: A signal that kills a running turn answers after the runner's SIGTERM grace (10 s).
SIGNAL_TIMEOUT_SECONDS = 60.0
WAIT_SECONDS = 120.0
POLL_INTERVAL_SECONDS = 0.5
FIXTURE_DIRECTORY = "e2e-fixtures"

SESSION_ROLE = "session"
FIRST_TURN = "Start here: the initiative's first message."
#: The killed turn's own scenario: it runs until a signal kills its process group.
HELD = "sleep_seconds: 90\n"
QUICK = "exit_code: 0\n"
FAILED = "exit_code: 1\n"
#: Long enough to observe a restarted turn still open, short enough to wait for.
BRIEF = "sleep_seconds: 6\n"

TEMPLATE = """name: @NAME@
version: 1
description: e2e epic 4 conversation stop
@TYPE@inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  first_turn:  { type: string,     required: false }
  round_steps: { type: string,     required: false }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: '{{base_branch}}', branch: 'e2e/talk-@NAME@' }
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
    writes: ["docs/@STEP@.md"]
    prompts:
      open: "Open @STEP@."
@CLOSE@"""

CLOSE = '      close: "Close @STEP@ as {attempt_id}."\n'

#: `$1` directory, `$2` name, `$3` manifest, `$4` the first turn's scenario, `$5` every
#: later turn's. The skill and the persona are repository paths the rows name.
MAKE_TALKING_ORIGIN = """
set -e
dir="$1"; name="$2"; manifest="$3"; first="$4"; rest="$5"
mkdir -p "$dir"
rm -rf "$dir/$name.git" "$dir/$name.seed"
git init --quiet --bare --initial-branch=main "$dir/$name.git"
git init --quiet --initial-branch=main "$dir/$name.seed"
cd "$dir/$name.seed"
git config user.email e2e@example.invalid
git config user.name e2e
echo "$name" > README.md
mkdir -p _bmad/_config .fake-harness personas skills/talk
printf '%s' "$manifest" > _bmad/_config/manifest.yaml
printf '%s' "$first" > .fake-harness/attempt-1.yaml
printf '%s' "$rest" > .fake-harness/default.yaml
printf 'The analyst.\\n' > personas/analyst.md
printf 'Talk the step through.\\n' > skills/talk/SKILL.md
git add --all
git commit --quiet --message seed
git push --quiet "$dir/$name.git" main:main
git --git-dir="$dir/$name.git" symbolic-ref HEAD refs/heads/main
"""


def template_text(
    name: str, steps: tuple[str, ...] = ("product", "ux"), *, kind: str = "interactive"
) -> str:
    rows = "".join(ROW.replace("@CLOSE@", CLOSE).replace("@STEP@", step) for step in steps)
    type_line = f"type: {kind}\n" if kind else ""
    return TEMPLATE.replace("@TYPE@", type_line).replace("@ROWS@", rows).replace("@NAME@", name)


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


def talking_origin(settings: Settings, first: str, rest: str) -> str:
    """A fresh bare origin scripting the fake harness; its `file://` URL.

    The container is tried first: a host that happens to have a writable `WORK_DIR` of its
    own would otherwise take the fixture, and the containerised backend would never see it.
    """
    directory = settings.work_dir / FIXTURE_DIRECTORY
    name = f"talk-{uuid4()}"
    arguments = [str(directory), name, manifest_stating(settings.bmad_version), first, rest]
    refusals: list[str] = []
    for prefix in (("docker", "compose", "exec", "-T", "backend-api"), ()):
        command = [*prefix, "sh", "-c", MAKE_TALKING_ORIGIN, "sh", *arguments]
        try:
            done = subprocess.run(  # fixed argv, no shell
                command,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=DOCKER_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            refusals.append(str(error))
            continue
        if done.returncode == 0:
            return f"file://{directory}/{name}.git"
        refusals.append((done.stderr or done.stdout).strip())
    pytest.fail("no route to create the conversation fixture: " + " | ".join(refusals))


def detail_of(api: httpx.Client, run_id: str) -> dict[str, Any]:
    response = api.get(f"{RUNS}/{run_id}/detail")
    assert response.status_code == HTTP_OK, response.text
    return dict(response.json())


def session_of(api: httpx.Client, run_id: str) -> dict[str, Any]:
    response = api.get(f"{RUNS}/{run_id}/session")
    assert response.status_code == HTTP_OK, response.text
    return dict(response.json())


def row(detail: dict[str, Any], path: str) -> dict[str, Any]:
    return next(step for step in detail["steps"] if step["path"] == path)


def wait_for[T](read: Callable[[], T], done: Callable[[T], bool], what: str) -> T:
    deadline = time.monotonic() + WAIT_SECONDS
    value = read()
    while not done(value) and time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        value = read()
    if not done(value):
        pytest.fail(f"{what} did not happen within {WAIT_SECONDS:.0f}s; last read: {value}")
    return value


def parked_on(api: httpx.Client, run_id: str, path: str) -> dict[str, Any]:
    """The Run's detail once it waits on `path` as a conversation stop."""

    def parked(detail: dict[str, Any]) -> bool:
        if detail["run"]["status"] in {"done", "failed", "cancelled"}:
            pytest.fail(f"run {run_id} ended {detail['run']['status']}: {detail['alert']}")
        alert = detail["alert"] or {}
        return (
            detail["run"]["status"] == "needs_you"
            and alert.get("park_kind") == "conversation"
            and row(detail, path)["status"] == "checkpoint"
        )

    return wait_for(lambda: detail_of(api, run_id), parked, f"run {run_id} parking on {path}")


def signal(
    api: httpx.Client, run_id: str, kind: str, stop: int | None = None, **payload: Any
) -> httpx.Response:
    body: dict[str, Any] = {"kind": kind, "payload": payload}
    if stop is not None:
        body["stop"] = stop
    return api.post(f"{RUNS}/{run_id}/signals", json=body, timeout=SIGNAL_TIMEOUT_SECONDS)


def turns_of(sessions: Any, run_id: str, path: str) -> list[Attempt]:
    """The `session` attempts of one row, oldest first, read from the stack's database."""
    with sessions() as session:
        step = next(
            entry
            for entry in SQLAlchemyStepRunRepository(session).list_for_run(UUID(run_id))
            if entry.path == path
        )
        attempts = SQLAlchemyAttemptRepository(session).list_for_row(step.id)
    return [attempt for attempt in attempts if attempt.role == SESSION_ROLE]


@pytest.fixture
def start_run(api: httpx.Client, settings: Settings) -> Iterator[Callable[..., str]]:
    """`start_run(first, rest, **inputs) -> run_id` on a fresh origin and template."""
    started: list[str] = []

    def start(first: str, rest: str, **inputs: str) -> str:
        repository_id = create_repository(
            api, create_project(api), talking_origin(settings, first, rest)
        )
        clone_check(api, repository_id)
        name = f"e2e-talk-{uuid4().hex}"
        stored = api.post(f"{TEMPLATES}/{name}/versions", json={"yaml": template_text(name)})
        assert stored.status_code == HTTP_CREATED, stored.text
        payload = run_payload(
            name,
            repository_id,
            project_id=project_id_of(api, repository_id),
            harness="fake",
            inputs=inputs,
        )
        response = api.post(RUNS, json=payload)
        assert response.status_code == HTTP_CREATED, response.text
        run_id = str(response.json()["run"]["id"])
        started.append(run_id)
        return run_id

    yield start
    for run_id in started:
        signal(api, run_id, "cancel", confirm=True)


# ── CAP-3: the kind in the template ──────────────────────────────────────────────────────


def test_a_conversation_row_validates_only_in_an_interactive_template(api: httpx.Client) -> None:
    name = f"e2e-talk-{uuid4().hex}"
    interactive = template_text(name)
    auto = template_text(name, kind="")
    no_close = interactive.replace(CLOSE.replace("@STEP@", "ux"), "")

    answers = {
        label: api.post(f"{TEMPLATES}/{name}/validate", json={"yaml": text})
        for label, text in (("interactive", interactive), ("auto", auto), ("no_close", no_close))
    }

    for response in answers.values():
        assert response.status_code == HTTP_OK, response.text
    assert answers["interactive"].json()["errors"] == []
    assert answers["auto"].json()["errors"], answers["auto"].json()
    assert answers["no_close"].json()["errors"], answers["no_close"].json()


def test_the_template_graph_draws_each_conversation_row(api: httpx.Client) -> None:
    name = f"e2e-talk-{uuid4().hex}"
    stored = api.post(f"{TEMPLATES}/{name}/versions", json={"yaml": template_text(name)})
    assert stored.status_code == HTTP_CREATED, stored.text

    response = api.get(f"{TEMPLATES}/{name}/1/graph")

    assert response.status_code == HTTP_OK, response.text
    nodes = [node for node in response.json()["nodes"] if node["kind"] == "conversation"]
    assert [node["id"] for node in nodes] == ["product", "ux"]


# ── CAP-1, CAP-3, CAP-4: the park opens its own session ──────────────────────────────────


def test_a_conversation_row_parks_and_opens_a_step_session_with_the_first_turn(
    api: httpx.Client, sessions: Any, start_run: Callable[..., str]
) -> None:
    run_id = start_run(QUICK, QUICK, first_turn=FIRST_TURN)

    detail = parked_on(api, run_id, "product")
    view = session_of(api, run_id)
    turns = turns_of(sessions, run_id, "product")

    assert detail["run"]["senior_session"] is True
    assert row(detail, "ux")["status"] == "planned"
    assert view["active"] is True
    assert view["scope"] == "step"
    assert view["scopes"] == ["step"]
    assert len(turns) == 1
    assert turns[0].message == FIRST_TURN
    records = [entry for entry in detail["gate_record"] if entry["event"] == "session_start"]
    assert len(records) == 1, detail["gate_record"]


def test_a_conversation_stop_refuses_every_way_past_it_but_its_own(
    api: httpx.Client, start_run: Callable[..., str]
) -> None:
    run_id = start_run(QUICK, QUICK)
    stop = parked_on(api, run_id, "product")["run"]["park_seq"]

    refused = {
        "plain skip_step": signal(api, run_id, "skip_step", stop),
        "forced skip_step without its stop": signal(api, run_id, "skip_step", forced=True),
        "skip_story": signal(api, run_id, "skip_story", stop, forced=True),
        "continue": signal(api, run_id, "continue", stop),
        "step_close without its stop": signal(api, run_id, "step_close"),
        "step_close for a stale stop": signal(api, run_id, "step_close", stop - 1),
    }

    for label, response in refused.items():
        assert response.status_code == HTTP_CONFLICT, (label, response.text)
    assert row(detail_of(api, run_id), "product")["status"] == "checkpoint"


def test_step_close_resumes_the_row_which_parks_again_without_a_second_first_turn(
    api: httpx.Client, sessions: Any, start_run: Callable[..., str]
) -> None:
    run_id = start_run(QUICK, QUICK)
    stop = parked_on(api, run_id, "product")["run"]["park_seq"]
    wait_for(
        lambda: session_of(api, run_id),
        lambda view: not view["turn_running"],
        "the first turn ending",
    )

    closed = signal(api, run_id, "step_close", stop)
    again = wait_for(
        lambda: parked_on(api, run_id, "product"),
        lambda detail: detail["run"]["park_seq"] > stop,
        "the row parking on a new stop",
    )
    stale = signal(api, run_id, "step_close", stop)

    assert closed.status_code == HTTP_OK, closed.text
    assert stale.status_code == HTTP_CONFLICT, stale.text
    assert len(turns_of(sessions, run_id, "product")) == 1
    closes = [entry for entry in again["gate_record"] if entry["event"] == "step_close"]
    assert [(entry["actor"], entry["text"]) for entry in closes] == [("machine", "step closed")]


def test_a_round_skips_the_rows_it_does_not_name_and_opens_its_own_with_the_first_turn(
    api: httpx.Client, sessions: Any, start_run: Callable[..., str]
) -> None:
    run_id = start_run(QUICK, QUICK, first_turn=FIRST_TURN, round_steps="ux")

    detail = parked_on(api, run_id, "ux")

    assert row(detail, "product")["status"] == "skipped"
    assert row(detail, "product")["reason"] == "not in this round"
    assert [turn.message for turn in turns_of(sessions, run_id, "ux")] == [FIRST_TURN]


# ── CAP-5: every message kept; forced skip and cancel while it talks ─────────────────────


def test_a_forced_skip_mid_turn_closes_the_queued_turns_and_the_walk_waits_for_the_killed_one(
    api: httpx.Client, sessions: Any, start_run: Callable[..., str]
) -> None:
    run_id = start_run(HELD, HELD)
    stop = parked_on(api, run_id, "product")["run"]["park_seq"]
    wait_for(
        lambda: turns_of(sessions, run_id, "product"),
        lambda turns: turns[0].status == "running",
        "the first turn running",
    )

    posted = [
        api.post(f"{RUNS}/{run_id}/session/messages", json={"text": text})
        for text in ("one more thing", "and another")
    ]
    skipped = signal(api, run_id, "skip_step", stop, forced=True)
    detail = parked_on(api, run_id, "ux")
    product = turns_of(sessions, run_id, "product")
    ux = turns_of(sessions, run_id, "ux")

    for response in posted:
        assert response.status_code == HTTP_ACCEPTED, response.text
        assert response.json()["status"] == "queued"
    assert skipped.status_code == HTTP_OK, skipped.text
    assert row(detail, "product")["status"] == "skipped"
    assert row(detail, "product")["reason"] == "skipped, forced"
    killed, *queued = product
    assert killed.ended_at is not None
    assert [(turn.status, turn.output_ref, turn.message) for turn in queued] == [
        ("error", "step skipped", "one more thing"),
        ("error", "step skipped", "and another"),
    ]
    assert [turn.message for turn in ux] == ["Open ux."]
    assert ux[0].started_at is not None
    assert ux[0].started_at >= killed.ended_at


def test_cancel_mid_turn_ends_the_run_and_closes_the_queued_turn(
    api: httpx.Client, sessions: Any, start_run: Callable[..., str]
) -> None:
    run_id = start_run(HELD, HELD)
    parked_on(api, run_id, "product")
    wait_for(
        lambda: turns_of(sessions, run_id, "product"),
        lambda turns: turns[0].status == "running",
        "the first turn running",
    )
    posted = api.post(f"{RUNS}/{run_id}/session/messages", json={"text": "keep this"})

    cancelled = signal(api, run_id, "cancel", confirm=True)
    wait_for(
        lambda: detail_of(api, run_id)["run"]["status"],
        lambda status: status == "cancelled",
        "the Run ending cancelled",
    )
    turns = wait_for(
        lambda: turns_of(sessions, run_id, "product"),
        lambda turns: all(turn.ended_at is not None for turn in turns),
        "every turn of the row ending",
    )

    assert posted.status_code == HTTP_ACCEPTED, posted.text
    assert cancelled.status_code == HTTP_OK, cancelled.text
    assert (turns[-1].status, turns[-1].output_ref, turns[-1].message) == (
        "error",
        "Run cancelled",
        "keep this",
    )


# ── CAP-6: restart a failed turn ─────────────────────────────────────────────────────────


def failed_and_closed(view: dict[str, Any]) -> bool:
    """The last turn failed and is closed: `status` is written before `ended_at` is."""
    return (
        bool(view["turns"]) and view["turns"][-1]["status"] == "error" and not view["turn_running"]
    )


def test_a_failed_turn_restarts_once_in_the_same_harness_session(
    api: httpx.Client, sessions: Any, start_run: Callable[..., str]
) -> None:
    run_id = start_run(FAILED, BRIEF, first_turn=FIRST_TURN)
    parked_on(api, run_id, "product")
    wait_for(
        lambda: session_of(api, run_id),
        failed_and_closed,
        "the first turn failing",
    )

    retried = api.post(f"{RUNS}/{run_id}/session/retry")
    while_open = api.post(f"{RUNS}/{run_id}/session/retry")
    view = wait_for(
        lambda: session_of(api, run_id),
        lambda view: view["turns"][-1]["status"] == "done",
        "the restarted turn ending",
    )
    after_success = api.post(f"{RUNS}/{run_id}/session/retry")
    failed, restarted = turns_of(sessions, run_id, "product")

    assert retried.status_code == HTTP_CREATED, retried.text
    assert retried.json()["message"] == FIRST_TURN
    assert while_open.status_code == HTTP_CONFLICT, while_open.text
    assert after_success.status_code == HTTP_CONFLICT, after_success.text
    assert [turn["status"] for turn in view["turns"]] == ["error", "done"]
    assert failed.session_id is not None
    assert restarted.session_id == failed.session_id


def test_retry_is_refused_once_no_session_is_open(
    api: httpx.Client, start_run: Callable[..., str]
) -> None:
    run_id = start_run(FAILED, QUICK)
    parked_on(api, run_id, "product")
    wait_for(
        lambda: session_of(api, run_id),
        failed_and_closed,
        "the first turn failing",
    )
    assert signal(api, run_id, "cancel", confirm=True).status_code == HTTP_OK

    response = api.post(f"{RUNS}/{run_id}/session/retry")

    assert response.status_code == HTTP_CONFLICT, response.text
