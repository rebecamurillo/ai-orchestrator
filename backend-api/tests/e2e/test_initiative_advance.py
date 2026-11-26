"""The initiative's advance against the running stack (initiative orchestrator-initiative-steps,
epic 8, SPEC CAP-1..CAP-5).

The unit suite proves each rule over the shared fakes. What only the running stack settles: a
spec Run that the real engine walks to `done` leaves an advance that the real
`advance_initiative` workflow consumes after the commit; the gate's verdict is stored on the
gate row's attempt in Postgres and read back by the advance; a `fail` verdict starts round 2
for its owners with the gate's body as their first turn; a `pass` verdict runs the build's
pre-flight against `spec/{slug}` on the real origin, then starts the merge Run, which merges,
pushes `main` and deletes `spec/{slug}` through the real git adapter; the merge's end creates
`feat/{slug}` at `main`'s tip on the origin and starts the build with the project's run
defaults, or waits on `no project budget` until `PUT …/run-defaults` retries it; a merge
conflict parks the merge Run on the walk lane, opens a step session with the merge agent's
skill, and the agent's turn that concludes the merge resumes it with `continue`.

Every package, template and slug is fresh, every origin a new bare repository this module
writes (hard rule 6: no shipped template and no hub `package/` is read). The fake harness is
scripted per dispatch: the spec turns and the gate read `.fake-harness/default.yaml`, the merge
agent `.fake-harness/merge/`, the merge session's turn `.fake-harness/resolve/` (its prompt
carries the sentence the fake harness keys a scenario by). Every initiative and Run the module
creates is cancelled when its test ends.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import yaml

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.infrastructure.db import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyStepRunRepository,
    create_engine_from,
    create_session_factory,
)
from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_initiatives import (
    HTTP_CONFLICT,
    HTTP_CREATED,
    HTTP_OK,
    INITIATIVES,
    SIGNAL_TIMEOUT_SECONDS,
    TERMINAL,
    TIMEOUT_SECONDS,
    branch_sha,
    hub_origin,
    in_stack,
    run_detail,
    wait_for,
)
from tests.e2e.test_run_creation import (
    PROJECTS,
    RUNS,
    TEMPLATES,
    clone_check,
    create_repository,
    run_payload,
)

PATH = "pkg"
FIRST_MESSAGE = "Start here: the advance's first message."
BUDGET = "5.00"
DEFAULTS: dict[str, Any] = {
    "default_budget_usd": BUDGET,
    "default_harness": "fake",
    "default_model": None,
    "default_autonomy": None,
    "default_senior_model": None,
}
NO_BUDGET = {**DEFAULTS, "default_budget_usd": None}

CONFLICT_FILE = "CONFLICT.md"
MERGE_SKILL = "staged-review"
RESOLVE_MESSAGE = "Keep both sides of CONFLICT.md: spec folder resolve, story id resolve."
PASS_GATE = "---\nstatus: pass\n---\nNo defects.\n"
FAIL_GATE = (
    "---\nstatus: fail\nowners: [intake]\n---\n"
    "- intake: the scope names no user\n"
    "- intake: no success measure\n"
)
DONE_STEP = "---\nstatus: done\n---\n# Step\n"
#: The sequence positions of the fixture package, and the round a failing gate opens.
SPEC_AT, MERGE_AT, BUILD_AT = 0, 1, 2
ROUND_TWO = 2
#: The row statuses a parked row reads: `checkpoint` on a conversation, `error` on a conflict.
STOPPED = frozenset({"checkpoint", "error", "blocked"})
UNKNOWN_KEY = "unknown key"
PUSH_NEEDS_INTERACTIVE = "git.push allow_default_branch needs type: interactive"

SPEC = """name: spec
version: 1
description: e2e epic 8 spec workflow
type: interactive
inputs:
  project:           { type: project,    required: true }
  repository:        { type: repository, required: true }
  base_branch:       { type: string,     required: true }
  slug:              { type: string,     required: true }
  branch:            { type: string,     required: true }
  first_turn:        { type: string,     required: false }
  round_steps:       { type: string,     required: false }
  initiative_folder: { type: string,     required: false }
  harness:           { type: string,     required: false }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: '{{base_branch}}', branch: '{{branch}}', mode: attach }
    gate: deterministic
  - id: intake
    uses: conversation
    role: plan
    gate: human
    with: { step: intake, skill: skills/talk/SKILL.md, persona: personas/analyst.md }
    expect:
      files: ["docs/intake.md"]
      success: [done]
      blocked: [blocked]
    writes: ["docs/intake.md", "epics.yaml"]
    prompts:
      open: "Open intake."
      close: "Close intake as {attempt_id}."
  - id: gate
    uses: agent
    role: spec-gate
    with: { harness: '{{harness}}', skill: spec-gate }
    prompts:
      dispatch: "Run {skill}."
      rendered: "Rendered at {path}."
    expect:
      files: ["docs/gate.md"]
      success: [pass, fail]
      blocked: [blocked]
    gate: liveness
  - id: push
    uses: git.push
    with: { branch: '{{branch}}' }
    gate: deterministic
"""

MERGE = """name: merge
version: 1
description: e2e epic 8 merge workflow
type: interactive
inputs:
  project:           { type: project,    required: true }
  repository:        { type: repository, required: true }
  base_branch:       { type: string,     required: true }
  slug:              { type: string,     required: true }
  branch:            { type: string,     required: true }
  initiative_folder: { type: string,     required: false }
  harness:           { type: string,     required: false }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: '{{base_branch}}', branch: '{{branch}}', mode: attach }
    gate: deterministic
  - id: merge-agent
    uses: agent
    role: implement
    with: { harness: '{{harness}}', skill: @SKILL@ }
    prompts:
      dispatch: "Prepare the merge: spec folder merge, story id merge."
      rendered: "Rendered at {path}."
    expect:
      files: ["docs/merge.md"]
      success: [done]
      blocked: [blocked]
    gate: liveness
  - id: merge
    uses: git.merge
    with: { from: 'spec/{{slug}}' }
    gate: deterministic
  - id: push
    uses: git.push
    with: { branch: '{{branch}}', allow_default_branch: true }
    retry: { max: 1, sync_first: true }
    gate: deterministic
  - id: cleanup
    uses: git.branch_delete
    with: { branch: 'spec/{{slug}}' }
    gate: deterministic
""".replace("@SKILL@", MERGE_SKILL)

BUILD_HEAD = """name: build
version: 1
description: e2e epic 8 build workflow
inputs:
  project:           { type: project,    required: true }
  repository:        { type: repository, required: true }
  base_branch:       { type: string,     required: true }
  slug:              { type: string,     required: true }
  branch:            { type: string,     required: true }
  initiative_folder: { type: string,     required: false }
  plan_model:        { type: string,     required: false }
  review_model:      { type: string,     required: false }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: '{{base_branch}}', branch: '{{branch}}', mode: attach }
    gate: deterministic
"""

#: A build whose plan reads nothing from the initiative folder: its pre-flight passes on any
#: `spec/{slug}`.
BUILD_PLAIN = (
    BUILD_HEAD
    + """  - id: note
    run: "true"
    gate: deterministic
"""
)

#: A build that loops over `{initiative_folder}/epics.yaml`: its pre-flight fails on a
#: `spec/{slug}` that holds none, which the advance turns into a fail owned by the tech step.
BUILD_EPICS = (
    BUILD_HEAD
    + """  - id: epics
    for_each: "{{initiative_folder}}/epics.yaml"
    as: epic
    steps:
      - id: note
        run: "true"
        gate: deterministic
"""
)

#: `$1` the origin's `file://` URL, `$2` the branch, `$3` a path, `$4` its content: one commit
#: on the branch's tip, pushed.
PUSH_CHANGE = """
set -e
tmp=$(mktemp -d)
git clone --quiet --branch "$2" "$1" "$tmp/c"
cd "$tmp/c"
git config user.email e2e@example.invalid
git config user.name e2e
printf '%s' "$4" > "$3"
git add --all
git commit --quiet --message "e2e change on $2"
git push --quiet origin "$2"
cd /
rm -rf "$tmp"
"""

#: `$1` the origin's `file://` URL, `$2` a ref, `$3` a path: the file's content at that ref.
SHOW_FILE = """
set -e
tmp=$(mktemp -d)
git clone --quiet "$1" "$tmp/c"
git -C "$tmp/c" show "origin/$2:$3"
rm -rf "$tmp"
"""

#: `$1` the origin's `file://` URL, `$2` the new branch, `$3` a path, `$4` its content: a
#: branch cut from `main` with one commit, pushed.
PUSH_SIDE_BRANCH = """
set -e
tmp=$(mktemp -d)
git clone --quiet "$1" "$tmp/c"
cd "$tmp/c"
git config user.email e2e@example.invalid
git config user.name e2e
git checkout --quiet -b "$2"
printf '%s' "$4" > "$3"
git add --all
git commit --quiet --message "e2e side"
git push --quiet origin "$2"
cd /
rm -rf "$tmp"
"""


def scenario(files: dict[str, str], *, commit: bool = False) -> str:
    """One dispatch of the fake harness, as the YAML document it reads."""
    document: dict[str, Any] = {
        "exit_code": 0,
        "files": [{"path": path, "content": text} for path, text in files.items()],
    }
    if commit:
        document["commit"] = True
    return yaml.safe_dump(document)


def hub_files(package: str, *, gate: str, build: str, spec_extra: dict[str, str]) -> dict[str, str]:
    """The hub's seed: the package, its three templates, and every fake-harness scenario."""
    spec_turn = {"docs/intake.md": DONE_STEP, "docs/gate.md": gate, **spec_extra}
    return {
        f"{PATH}/package.yaml": (
            f"name: {package}\nsequence:\n"
            "  - { workflow: spec, template: templates/spec.yaml }\n"
            "  - { workflow: merge, template: templates/merge.yaml }\n"
            "  - { workflow: build, template: templates/build.yaml }\n"
            "gate: { pass: [pass], fail: [fail], owners_key: owners }\n"
            "status_map: { final: done, blocked: waiting for her }\n"
        ),
        f"{PATH}/templates/spec.yaml": SPEC,
        f"{PATH}/templates/merge.yaml": MERGE,
        f"{PATH}/templates/build.yaml": build,
        CONFLICT_FILE: "base\n",
        ".fake-harness/default.yaml": scenario(spec_turn),
        ".fake-harness/merge/default.yaml": scenario({"docs/merge.md": DONE_STEP}),
        ".fake-harness/resolve/default.yaml": scenario(
            {CONFLICT_FILE: "main side and spec side\n"}, commit=True
        ),
        "personas/analyst.md": "The analyst.\n",
        "skills/talk/SKILL.md": "Talk the step through.\n",
    }


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


class Hub:
    """A project with run defaults, a clone-checked hub and its installed fixture package."""

    def __init__(
        self,
        api: httpx.Client,
        settings: Settings,
        *,
        gate: str = PASS_GATE,
        build: str = BUILD_PLAIN,
        spec_extra: dict[str, str] | None = None,
    ) -> None:
        self.api = api
        self.package = f"e2e-adv-{uuid4().hex[:12]}"
        created = api.post(PROJECTS, json={"name": f"e2e advance {uuid4()}"})
        assert created.status_code == HTTP_CREATED, created.text
        self.project_id = str(created.json()["id"])
        self.set_defaults(DEFAULTS)
        files = hub_files(self.package, gate=gate, build=build, spec_extra=spec_extra or {})
        self.url = hub_origin(settings, files)
        self.repository_id = create_repository(api, self.project_id, self.url)
        clone_check(api, self.repository_id)
        installed = api.put(
            f"{PROJECTS}/{self.project_id}/package",
            json={"repository_id": self.repository_id, "path": PATH, "ref": "main"},
        )
        assert installed.status_code == HTTP_OK, installed.text
        self.created: list[str] = []

    def set_defaults(self, defaults: dict[str, Any]) -> None:
        response = self.api.put(f"{PROJECTS}/{self.project_id}/run-defaults", json=defaults)
        assert response.status_code == HTTP_OK, response.text

    def new(self) -> dict[str, Any]:
        response = self.api.post(
            INITIATIVES,
            json={
                "project_id": self.project_id,
                "name": f"Advance {uuid4().hex[:8]}",
                "first_message": FIRST_MESSAGE,
            },
            timeout=SIGNAL_TIMEOUT_SECONDS,
        )
        assert response.status_code == HTTP_CREATED, response.text
        self.created.append(str(response.json()["id"]))
        return dict(response.json())

    def cleanup(self) -> None:
        for initiative_id in self.created:
            self.api.post(f"{INITIATIVES}/{initiative_id}/cancel", timeout=SIGNAL_TIMEOUT_SECONDS)


@pytest.fixture
def make_hub(api: httpx.Client, settings: Settings) -> Iterator[Callable[..., Hub]]:
    made: list[Hub] = []

    def make(**options: Any) -> Hub:
        hub = Hub(api, settings, **options)
        made.append(hub)
        return hub

    yield make
    for hub in made:
        hub.cleanup()


def detail_of(api: httpx.Client, initiative_id: str) -> dict[str, Any]:
    response = api.get(f"{INITIATIVES}/{initiative_id}")
    assert response.status_code == HTTP_OK, response.text
    return dict(response.json())


def signal(api: httpx.Client, run_id: str, kind: str, stop: int | None = None) -> httpx.Response:
    body: dict[str, Any] = {"kind": kind, "payload": {}}
    if stop is not None:
        body["stop"] = stop
    return api.post(f"{RUNS}/{run_id}/signals", json=body, timeout=SIGNAL_TIMEOUT_SECONDS)


def session_of(api: httpx.Client, run_id: str) -> dict[str, Any]:
    response = api.get(f"{RUNS}/{run_id}/session")
    assert response.status_code == HTTP_OK, response.text
    return dict(response.json())


def run_at(api: httpx.Client, initiative_id: str, round_: int, position: int) -> dict[str, Any]:
    """The initiative's Run of `(round, position)`, once the advance has created it."""

    def find(detail: dict[str, Any]) -> dict[str, Any] | None:
        return next(
            (r for r in detail["runs"] if (r["round"], r["position"]) == (round_, position)),
            None,
        )

    detail = wait_for(
        lambda: detail_of(api, initiative_id),
        lambda found: find(found) is not None,
        f"initiative {initiative_id} creating its Run of round {round_} position {position}",
    )
    found = find(detail)
    assert found is not None
    return found


def ended(api: httpx.Client, run_id: str) -> dict[str, Any]:
    return wait_for(
        lambda: run_detail(api, run_id),
        lambda detail: detail["run"]["status"] in TERMINAL,
        f"run {run_id} ending",
    )


def parked(api: httpx.Client, run_id: str, kind: str, path: str) -> dict[str, Any]:
    """The Run's detail once it waits on `path` for a `kind` stop."""

    def stopped(detail: dict[str, Any]) -> bool:
        if detail["run"]["status"] in TERMINAL:
            pytest.fail(f"run {run_id} ended {detail['run']['status']}: {detail['alert']}")
        alert = detail["alert"] or {}
        return (
            detail["run"]["status"] == "needs_you"
            and alert.get("park_kind") == kind
            and step_row(detail, path)["status"] in STOPPED
        )

    return wait_for(lambda: run_detail(api, run_id), stopped, f"run {run_id} parking {kind}")


def close_intake(api: httpx.Client, run_id: str) -> None:
    """Wait for the intake's first turn to end, then close the step on its stop."""
    stop = parked(api, run_id, "conversation", "intake")["run"]["park_seq"]
    wait_for(
        lambda: session_of(api, run_id),
        lambda view: len(view["turns"]) >= 1 and not view["turn_running"],
        f"run {run_id}'s first intake turn ending",
    )
    closed = signal(api, run_id, "step_close", stop)
    assert closed.status_code == HTTP_OK, closed.text


def spec_run_id(created: dict[str, Any]) -> str:
    return str(created["runs"][0]["id"])


def gate_attempt(sessions: Any, run_id: str) -> Attempt:
    """The latest attempt of the Run's `spec-gate` row, read from the stack's database."""
    with sessions() as session:
        row = next(
            step
            for step in SQLAlchemyStepRunRepository(session).list_for_run(UUID(run_id))
            if step.role == "spec-gate"
        )
        attempts = SQLAlchemyAttemptRepository(session).list_for_row(row.id)
    assert attempts, f"no attempt on the gate row of run {run_id}"
    return attempts[-1]


def show(url: str, branch: str, path: str) -> str:
    return in_stack(SHOW_FILE, url, branch, path)


def records(detail: dict[str, Any], event: str) -> list[tuple[str, str]]:
    return [(e["actor"], e["text"]) for e in detail["gate_record"] if e["event"] == event]


def step_row(detail: dict[str, Any], path: str) -> dict[str, Any]:
    return next(step for step in detail["steps"] if step["path"] == path)


# ── CAP-1, CAP-2, CAP-3: a failing gate reopens its owners ─────────────────────────────


def test_a_failing_gate_is_stored_on_its_row_and_starts_round_2_for_its_owners(
    api: httpx.Client, sessions: Any, make_hub: Callable[..., Hub]
) -> None:
    hub = make_hub(gate=FAIL_GATE)
    created = hub.new()
    spec_id = spec_run_id(created)

    close_intake(api, spec_id)

    assert ended(api, spec_id)["run"]["status"] == "done"
    verdict = gate_attempt(sessions, spec_id)
    assert verdict.verdict_word == "fail"
    assert verdict.verdict_fields is not None
    assert verdict.verdict_fields["owners"] == ["intake"]
    assert verdict.verdict_text is not None
    assert "- intake: the scope names no user" in verdict.verdict_text
    assert "status: fail" not in verdict.verdict_text

    round_two = run_at(api, created["id"], 2, 0)
    assert round_two["template_name"] == f"{hub.package}.spec"
    inputs = run_detail(api, round_two["id"])["run"]["inputs"]
    assert inputs["round_steps"] == "intake"
    assert inputs["first_turn"] == verdict.verdict_text
    assert inputs["branch"] == f"spec/{created['slug']}"
    assert detail_of(api, created["id"])["round"] == ROUND_TWO
    assert [r for r in detail_of(api, created["id"])["runs"] if r["position"] == MERGE_AT] == []

    parked(api, round_two["id"], "conversation", "intake")
    detail = wait_for(
        lambda: detail_of(api, created["id"]),
        lambda found: any(
            turn["author"] == "gate"
            for workflow in found["workflows"]
            for step in workflow["steps"]
            if step["id"] == "intake"
            for turn in step["turns"]
        ),
        "the round-2 intake turn reading author gate",
    )
    intake = next(s for s in detail["workflows"][0]["steps"] if s["id"] == "intake")
    [gate_turn] = [turn for turn in intake["turns"] if turn["author"] == "gate"]
    assert (gate_turn["round"], gate_turn["defects"], gate_turn["owner"]) == (2, 2, "intake")


def test_a_pass_whose_build_preflight_finds_no_epics_list_reopens_the_tech_step(
    api: httpx.Client, sessions: Any, make_hub: Callable[..., Hub]
) -> None:
    hub = make_hub(gate=PASS_GATE, build=BUILD_EPICS)
    created = hub.new()
    spec_id = spec_run_id(created)

    close_intake(api, spec_id)

    assert ended(api, spec_id)["run"]["status"] == "done"
    assert gate_attempt(sessions, spec_id).verdict_word == "pass"
    round_two = run_at(api, created["id"], 2, 0)
    inputs = run_detail(api, round_two["id"])["run"]["inputs"]
    assert inputs["round_steps"] == "intake"
    assert "epics.yaml" in inputs["first_turn"]
    assert [r for r in detail_of(api, created["id"])["runs"] if r["position"] != SPEC_AT] == []


# ── CAP-3, CAP-5: a passing gate merges, then builds from main ─────────────────────────


def test_a_passing_gate_merges_into_main_then_builds_on_feat_from_main(
    api: httpx.Client, sessions: Any, make_hub: Callable[..., Hub]
) -> None:
    hub = make_hub(gate=PASS_GATE)
    created = hub.new()
    slug = created["slug"]
    spec_id = spec_run_id(created)

    close_intake(api, spec_id)
    spec = ended(api, spec_id)
    assert spec["run"]["status"] == "done"
    assert gate_attempt(sessions, spec_id).verdict_word == "pass"

    merge_ref = run_at(api, created["id"], 1, 1)
    assert merge_ref["template_name"] == f"{hub.package}.merge"
    merge = ended(api, merge_ref["id"])
    assert merge["run"]["status"] == "done", merge["alert"]
    assert merge["template_type"] == "interactive"
    assert merge["run"]["inputs"]["branch"] == "main"
    assert merge["run"]["inputs"]["slug"] == slug
    assert merge["run"]["inputs"]["initiative_folder"] == "initiatives"
    assert Decimal(merge["run"]["budget_usd"]) == Decimal(spec["run"]["budget_usd"])

    assert show(hub.url, "main", "docs/gate.md") == PASS_GATE
    assert branch_sha(hub.url, f"spec/{slug}") == ""
    build_ref = run_at(api, created["id"], 1, 2)
    # the advance pushes feat/{slug} just before it creates the build Run, after the merge ends
    assert branch_sha(hub.url, f"feat/{slug}") == branch_sha(hub.url, "main")
    assert build_ref["template_name"] == f"{hub.package}.build"
    build = ended(api, build_ref["id"])
    assert build["run"]["status"] == "done", build["alert"]
    assert Decimal(build["run"]["budget_usd"]) == Decimal(BUDGET)
    inputs = build["run"]["inputs"]
    assert inputs["slug"] == slug
    assert inputs["branch"] == f"feat/{slug}"
    assert inputs["initiative_folder"] == f"initiatives/{slug}"
    assert "plan_model" not in inputs
    assert "review_model" not in inputs

    final = detail_of(api, created["id"])
    assert sorted((r["round"], r["position"]) for r in final["runs"]) == [(1, 0), (1, 1), (1, 2)]
    assert final["round"] == 1


def test_a_merge_with_no_project_budget_waits_until_the_run_defaults_set_one(
    api: httpx.Client, make_hub: Callable[..., Hub]
) -> None:
    hub = make_hub(gate=PASS_GATE)
    created = hub.new()
    slug = created["slug"]
    spec_id = spec_run_id(created)
    parked(api, spec_id, "conversation", "intake")
    hub.set_defaults(NO_BUDGET)

    close_intake(api, spec_id)
    merge_ref = run_at(api, created["id"], 1, 1)
    assert ended(api, merge_ref["id"])["run"]["status"] == "done"

    waiting = wait_for(
        lambda: detail_of(api, created["id"]),
        lambda found: found["reason"] == "no project budget",
        "the build's advance reading no project budget",
    )
    assert waiting["status"] == "waiting for her"
    assert [r for r in waiting["runs"] if r["position"] == BUILD_AT] == []
    assert branch_sha(hub.url, f"feat/{slug}") == ""

    hub.set_defaults(DEFAULTS)

    build_ref = run_at(api, created["id"], 1, 2)
    assert Decimal(run_detail(api, build_ref["id"])["run"]["budget_usd"]) == Decimal(BUDGET)
    assert branch_sha(hub.url, f"feat/{slug}") == branch_sha(hub.url, "main")
    assert detail_of(api, created["id"])["reason"] != "no project budget"


# ── CAP-4: a merge conflict is a conversation with the merge agent ─────────────────────


def test_a_merge_conflict_opens_a_session_with_the_merge_skill_and_the_agents_turn_resumes_it(
    api: httpx.Client, sessions: Any, make_hub: Callable[..., Hub]
) -> None:
    hub = make_hub(gate=PASS_GATE, spec_extra={CONFLICT_FILE: "spec side\n"})
    created = hub.new()
    slug = created["slug"]
    spec_id = spec_run_id(created)
    in_stack(PUSH_CHANGE, hub.url, "main", CONFLICT_FILE, "main side\n")

    close_intake(api, spec_id)
    merge_id = run_at(api, created["id"], 1, 1)["id"]

    stop = parked(api, merge_id, "merge_conflict", "merge")
    assert stop["alert"]["reason"] == f"merge conflict: spec/{slug} into main"
    assert stop["run"]["senior_session"] is True
    view = session_of(api, merge_id)
    assert view["active"] is True
    assert view["scope"] == "step"
    assert {"continue", "retry", "cancel"} <= set(stop["admitted_signals"])
    queue = api.get("/api/v1/queue")
    assert queue.status_code == HTTP_OK, queue.text
    [held] = [item for item in queue.json()["items"] if item["run"]["id"] == merge_id]
    assert held["lane"] == "walk"
    merge_step = next(
        step
        for workflow in detail_of(api, created["id"])["workflows"]
        for step in workflow["steps"]
        if step["id"] == "merge"
    )
    assert CONFLICT_FILE in merge_step["conflict_files"]

    # outside a conversation a session takes one turn at a time: the opening turn ends first
    wait_for(
        lambda: session_of(api, merge_id),
        lambda view: not view["turn_running"],
        f"run {merge_id}'s opening merge turn ending",
    )
    posted = api.post(f"{RUNS}/{merge_id}/session/messages", json={"text": RESOLVE_MESSAGE})
    assert posted.is_success, posted.text

    resumed = wait_for(
        lambda: run_detail(api, merge_id),
        lambda detail: bool(records(detail, "continue")),
        "the machine's continue after the merge agent's turn",
    )
    assert records(resumed, "continue") == [("machine", "merge resumed after the agent's turn")]
    with sessions() as session:
        row = next(
            step
            for step in SQLAlchemyStepRunRepository(session).list_for_run(UUID(merge_id))
            if step.path == "merge"
        )
        turns = [
            attempt
            for attempt in SQLAlchemyAttemptRepository(session).list_for_row(row.id)
            if attempt.role == "session"
        ]
    assert turns, "no session turn on the merge row"
    assert turns[0].log_path is not None
    prompt = in_stack('cat "$1"', f"{turns[0].log_path}.prompt")
    assert prompt.splitlines()[0].startswith(f"{MERGE_SKILL} ")

    merge = ended(api, merge_id)
    assert merge["run"]["status"] == "done", merge["alert"]
    # AD-13's `done · already merged` is the row's status and its reason
    merged = step_row(merge, "merge")
    assert (merged["status"], merged["reason"]) == ("done", "already merged")
    assert show(hub.url, "main", CONFLICT_FILE) == "main side and spec side\n"
    assert branch_sha(hub.url, f"spec/{slug}") == ""
    run_at(api, created["id"], 1, 2)


def test_a_merge_conflict_outside_an_initiative_opens_no_session_and_refuses_continue(
    api: httpx.Client, settings: Settings
) -> None:
    created = api.post(PROJECTS, json={"name": f"e2e plain merge {uuid4()}"})
    assert created.status_code == HTTP_CREATED, created.text
    project_id = str(created.json()["id"])
    url = hub_origin(settings, {CONFLICT_FILE: "base\n", ".fake-harness/default.yaml": "{}\n"})
    in_stack(PUSH_SIDE_BRANCH, url, "side", CONFLICT_FILE, "side\n")
    in_stack(PUSH_CHANGE, url, "main", CONFLICT_FILE, "main side\n")
    repository_id = create_repository(api, project_id, url)
    clone_check(api, repository_id)
    name = f"e2e-plain-merge-{uuid4().hex}"
    text = (
        f"name: {name}\nversion: 1\ndescription: e2e epic 8 plain merge\n"
        "inputs:\n"
        "  project:     { type: project,    required: true }\n"
        "  repository:  { type: repository, required: true }\n"
        "  base_branch: { type: string,     required: true }\n"
        "steps:\n"
        "  - id: checkout\n"
        "    uses: git.worktree\n"
        f"    with: {{ base: '{{{{base_branch}}}}', branch: 'e2e/{name}' }}\n"
        "    gate: deterministic\n"
        "  - id: merge\n"
        "    uses: git.merge\n"
        "    with: { from: side }\n"
        "    gate: deterministic\n"
    )
    stored = api.post(f"{TEMPLATES}/{name}/versions", json={"yaml": text})
    assert stored.status_code == HTTP_CREATED, stored.text
    response = api.post(
        RUNS, json=run_payload(name, repository_id, project_id=project_id, harness="fake")
    )
    assert response.status_code == HTTP_CREATED, response.text
    run_id = str(response.json()["run"]["id"])
    try:
        stop = parked(api, run_id, "merge_conflict", "merge")

        # RunOut drops `senior_session` at its default, False (api/schemas/common.py drop_default)
        assert stop["run"].get("senior_session", False) is False
        assert session_of(api, run_id)["active"] is False
        assert "continue" not in stop["admitted_signals"]
        assert {"retry", "cancel"} <= set(stop["admitted_signals"])
        refused = signal(api, run_id, "continue", stop["run"]["park_seq"])
        assert refused.status_code == HTTP_CONFLICT, refused.text
        assert run_detail(api, run_id)["run"]["park_seq"] == stop["run"]["park_seq"]
    finally:
        api.post(
            f"{RUNS}/{run_id}/signals",
            json={"kind": "cancel", "payload": {"confirm": True}},
            timeout=SIGNAL_TIMEOUT_SECONDS,
        )


# ── CAP-3: the two git.push keys are declared, and checked by the validator ────────────


def _reasons(api: httpx.Client, text: str) -> list[str]:
    response = api.post(f"{TEMPLATES}/e2e-push-keys-{uuid4().hex}/validate", json={"yaml": text})
    assert response.status_code == HTTP_OK, response.text
    return [str(error["reason"]) for error in response.json()["errors"]]


def test_the_validator_admits_the_push_keys_only_where_they_are_declared(
    api: httpx.Client,
) -> None:
    head = "name: push\nversion: 1\n"
    push = (
        "steps:\n  - id: p\n    uses: git.push\n    gate: deterministic\n"
        "    with: { branch: main, allow_default_branch: true }\n"
        "    retry: { max: 2, sync_first: true }\n"
    )
    commit = (
        "steps:\n  - id: c\n    uses: git.commit\n    gate: deterministic\n"
        "    with: { message: m }\n    retry: { max: 1, sync_first: true }\n"
    )

    assert _reasons(api, head + "type: interactive\n" + push) == []
    assert PUSH_NEEDS_INTERACTIVE in _reasons(api, head + push)
    assert UNKNOWN_KEY in _reasons(api, head + commit)
