"""UJ-3, proven end to end on the scripted harness (6.8, SPEC CAP-8, FR-18..FR-20, SM-2).

Every gate Epic 6 built has a scenario of its own already. What none of them settles is that
the *journey* works — that one Run walks blocked → Answer → done, stops again at a spec
checkpoint and carries on from a Continue, fails its quality gate twice on the last Story,
lets the Operator repair a file inline and give up on that Story, and ends `done` naming
what was skipped. A sequence can be broken while every step of it passes alone: the recurring
defect of this codebase is a signal effect that moves a row and enqueues nothing, and that is
invisible to any test that stops one signal later.

**Four scenarios, two Runs.** A, B and C are one Run because SPEC CAP-8's own success signal
is one Run — "she opens it, reads the question … at story 4-2 the Run pauses at the spec
checkpoint … story 4-3's verify fails twice and she skips it; by evening the card reads DON
… with 4-3 listed as skipped". D is the brief's own "second Run", started only once the
journey Run is terminal, so this module never holds more than one of `MAX_ACTIVE_RUNS`.

**Everything here is an HTTP call an Operator could make.** No row is written, no worktree is
touched, no process is patched. The two reads that go past the API — the `trajectory` table
and the branch's own commits — are reads of what the product left behind.

Needs `ORCH_TEST_MODE=1` on the stack (`docker-compose.e2e.yml` sets it, `make e2e` uses it);
`test_mode` fails by name rather than skipping, because a gate that skips reports success for
a suite that ran nothing. Both Runs end terminal, so neither holds a global slot afterwards
(AD-12).
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text

from orchestrator.infrastructure.db import (
    SQLAlchemyRunRepository,
    create_engine_from,
    create_session_factory,
)
from orchestrator.infrastructure.settings import Settings
from tests.e2e.helpers.gates_fixture import epic_template_as
from tests.e2e.helpers.uj3_reads import Uj3Reads
from tests.e2e.test_answer_signal import detail_of, poll_until, step_status
from tests.e2e.test_run_creation import PROJECTS, RUNS, clone_check, create_project
from tests.e2e.test_signals import run_check

pytestmark = pytest.mark.uj3

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_CONFLICT = 409
TIMEOUT_SECONDS = 10.0

SPEC_FOLDER = "specs/gates"
DECLARED_BRANCH = "epics/gates"

#: This journey's own quality gate: the one whose file lives inside the spec folder, so the
#: Operator's repair in scenario C is a real `PUT /runs/{id}/files` (see the fixture README).
QUALITY_GATE = "sh check-spec.sh"
GATE_FILE = f"{SPEC_FOLDER}/GATE_OK"

STORY_1_BUILD = "stories[0].build"
STORY_1_VERIFY = "stories[0].verify"
STORY_1_COMMIT_GUARD = "stories[0].commit-guard"
STORY_2_BUILD = "stories[1].build"
STORY_2_COMMIT_GUARD = "stories[1].commit-guard"
STORY_3_BUILD = "stories[2].build"
STORY_3_VERIFY = "stories[2].verify"
STORY_3_COMMIT_GUARD = "stories[2].commit-guard"
STORY_3_CHECKPOINT = "stories[2].after"

STORY_1_FILE = f"{SPEC_FOLDER}/stories/1-notify.md"
STORY_1_ARCHIVED = f"{SPEC_FOLDER}/stories/.answers/1-attempt-1.md"
STORY_2_FILE = f"{SPEC_FOLDER}/stories/2-plan.md"
STORY_3_FILE = f"{SPEC_FOLDER}/stories/3-ship.md"

#: The scripted agent's own words, from `.fake-harness/1/attempt-1.yaml`.
CONDITION = "intent gap"
QUESTION = "Where should the notification be posted?"
ANSWER = "Post to the project's channel only"
ANSWER_CLAUSE = f'Answer from the operator to the blocking condition "{CONDITION}": {ANSWER}'

#: `application/steps/agent.py::HALT`, the clause a Continue must *not* re-send (6.2).
HALT_SUFFIX = "Halt after planning."

#: `application/steps/git_commit.py::NO_CHANGES` — story 1's own commit guard, because the
#: scripted harness already committed everything the Answer unblocked.
NO_CHANGES = "no changes"

#: `apply_step_result.py::VERIFY_FAILED` with `story.yaml`'s own `on_fail.max = 1`.
VERIFY_FAILED = "verify failed 2/2"

#: `signal_effects.py::SKIPPED_BY_OPERATOR` / `SKIP_MESSAGE`, as they reach the read model
#: and the branch.
SKIPPED_BY_OPERATOR = "skipped by operator"
SKIP_COMMIT_SUBJECT = "story 3: skipped by operator"

#: `application/steps/agent.py::PREPARE_MESSAGE` for story 3's redispatch — the commit that
#: holds the Story file as the redispatch saw it, before the harness overwrote it.
PREPARE_ATTEMPT_2 = "orchestrator: prepare story 3 attempt 2"

#: FR-18's timing, as the brief states it: the Run is `running` on the next API read.
ONE_POLL_SECONDS = 5.0

ATTEMPTS_AFTER_A_RESUME = 2


# ── the stack, the fixture, and the reporter ────────────────────────────────────────────


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture(scope="module")
def bmad_version() -> str:
    value = os.environ.get("BMAD_VERSION")
    if not value:
        pytest.fail(
            "BMAD_VERSION is not set: the gates fixture's `_bmad/` manifest has to state the "
            "version this instance pins (`make e2e` exports it from .env.e2e)"
        )
    return value


@pytest.fixture(scope="module")
def gates(settings: Settings, bmad_version: str) -> Uj3Reads:
    return Uj3Reads(settings.work_dir, bmad_version)


@pytest.fixture(scope="module")
def sessions(settings: Settings) -> Any:
    """A session factory against the same database the stack writes — the `trajectory`
    table has no API surface, and the Run's own `worktrees` are read back for scenario D."""
    return create_session_factory(create_engine_from(settings))


@pytest.fixture(scope="module")
def test_mode(api: httpx.Client) -> None:
    """Fail by name when the stack is not in test mode, rather than timing out later."""
    response = api.get("/api/v1/harnesses")
    assert response.status_code == HTTP_OK, response.text
    rows = {item["name"]: item for item in response.json()["items"]}
    assert "fake" in rows, (
        "the `fake` harness is not seeded: this gate needs ORCH_TEST_MODE=1 on the stack "
        "(docker-compose.e2e.yml sets it; `make e2e` is the target that uses it)"
    )
    assert rows["fake"]["enabled"] is True, rows["fake"]


@pytest.fixture(scope="module")
def report(request: pytest.FixtureRequest) -> Any:
    """Write past pytest's capture, so the gate record is printed on a pass too (AC1).

    The terminal reporter is the plugin that owns the terminal; writing through it is the
    difference between "printed" and "printed if something failed".
    """
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")

    def write(line: str) -> None:
        if reporter is None:  # pragma: no cover — pytest always registers it
            return
        reporter.write_line(line)

    return write


def print_gate_record(report: Any, what: str, detail: dict[str, Any]) -> None:
    """Every gate record line of one Run, in order — the brief's own AC1."""
    report(f"\n── {what}: gate record ({detail['run']['id']}) ──")
    for entry in detail["gate_record"]:
        report(
            f"  {entry['at']}  {entry['event']:<12} {entry['actor']:<8} "
            f"{entry['path'] or '-':<28} {entry['text'] or ''}"
        )


def start_journey_run(api: httpx.Client, gates: Uj3Reads, name: str) -> str:
    """A fresh gates clone, a Template of this suite's own, and a Run on the `fake` harness.

    `epic_template_as` rather than `epic@1` itself: `test_templates.py` asserts nothing pins
    `epic@1`, and this suite has to pass twice against the same stack.
    """
    project_id = create_project(api)
    created = api.post(
        f"{PROJECTS}/{project_id}/repositories",
        json={
            "url": gates.make(),
            "default_branch": "main",
            "quality_gate_command": QUALITY_GATE,
            # operator revision 2026-09-15: since the quality-gate reorder (b0f3898) the
            # story's verify row runs `unit_test_command`; declaring it keeps verify
            # exercised — without it the row plans `skipped · no command`.
            "unit_test_command": QUALITY_GATE,
        },
    )
    assert created.status_code == HTTP_CREATED, created.text
    repository_id = str(created.json()["id"])
    clone_check(api, repository_id)

    template_name = f"e2e-{name}-{uuid4().hex}"
    saved = api.post(
        f"/api/v1/templates/{template_name}/versions",
        json={"yaml": epic_template_as(template_name)},
    )
    assert saved.status_code == HTTP_CREATED, saved.text

    started = api.post(
        RUNS,
        json={
            "template_name": template_name,
            "template_version": 1,
            "project_id": project_id,
            "repository_id": repository_id,
            "base_branch": "main",
            "budget_usd": "5",
            "harness": "fake",
            "inputs": {"spec_folder": SPEC_FOLDER, "branch": f"{DECLARED_BRANCH}-{uuid4().hex}"},
        },
    )
    assert started.status_code == HTTP_CREATED, started.text
    return str(started.json()["run"]["id"])


def wait_blocked_on_story_1(api: httpx.Client, run_id: str) -> dict[str, Any]:
    return poll_until(
        api,
        run_id,
        lambda detail: (
            detail["run"]["status"] == "needs_you"
            and step_status(detail, STORY_1_BUILD) == "blocked"
        ),
        "the Run parking blocked on story 1",
    )


# ── scenario A: blocked → answer → done ─────────────────────────────────────────────────


@pytest.fixture(scope="module")
def blocked(
    api: httpx.Client, gates: Uj3Reads, test_mode: None, report: Any
) -> Iterator[dict[str, Any]]:
    """The journey Run, walked until story 1's agent parks `blocked`."""
    started_at = time.monotonic()
    run_id = start_journey_run(api, gates, "uj3")
    try:
        detail = wait_blocked_on_story_1(api, run_id)
        report(f"\n[uj3] parked blocked in {time.monotonic() - started_at:.1f}s")
        yield {"id": run_id, "detail": detail, "started_at": started_at}
    finally:
        api.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel", "payload": {"confirm": True}})


def test_a_the_run_parks_blocked_carrying_the_agents_own_question(
    blocked: dict[str, Any],
) -> None:
    """The stop the Operator comes back to: `BLK`, and the question in the body."""
    detail = blocked["detail"]

    assert detail["run"]["status"] == "needs_you"
    assert detail["alert"]["park_kind"] == "blocked"
    assert detail["alert"]["token"] == "BLK"
    assert CONDITION in detail["alert"]["reason"]
    assert QUESTION in detail["alert"]["reason"]
    assert "answer" in detail["admitted_signals"]


@pytest.fixture(scope="module")
def answered(api: httpx.Client, blocked: dict[str, Any]) -> dict[str, Any]:
    """The Answer, the very next API read, and the Run walked on to story 1's commit guard."""
    run_id = blocked["id"]
    signalled_at = time.monotonic()
    response = api.post(
        f"{RUNS}/{run_id}/signals", json={"kind": "answer", "payload": {"text": ANSWER}}
    )
    assert response.status_code == HTTP_OK, response.text
    next_read = detail_of(api, run_id)
    elapsed = time.monotonic() - signalled_at
    resumed = poll_until(
        api,
        run_id,
        lambda detail: step_status(detail, STORY_1_COMMIT_GUARD) == "done",
        "story 1 reaching its commit guard after the Answer",
    )
    return {
        "signalled": response.json()["status"],
        "next_read": next_read,
        "elapsed": elapsed,
        "detail": resumed,
    }


def test_a_the_answer_puts_the_run_back_to_running_within_one_poll(
    answered: dict[str, Any],
) -> None:
    """FR-18's timing, measured rather than assumed: the signal response already says
    `running`, and so does the first read that follows it, inside one poll interval."""
    assert answered["signalled"] == "running"
    assert answered["next_read"]["run"]["status"] == "running"
    assert answered["elapsed"] <= ONE_POLL_SECONDS, answered["elapsed"]


def test_a_the_question_is_archived_with_the_operators_answer_under_it(
    answered: dict[str, Any], gates: Uj3Reads
) -> None:
    worktree = answered["detail"]["run"]["worktree_path"]

    archived = gates.show(worktree, "HEAD", STORY_1_ARCHIVED)

    assert f"Blocking condition: {CONDITION}" in archived
    assert "## Human Answer" in archived
    assert archived.rstrip().endswith(ANSWER)


def test_a_the_re_dispatch_carried_the_answer_clause_and_the_story_was_replanned(
    answered: dict[str, Any], gates: Uj3Reads
) -> None:
    """The glob was empty at the second dispatch, so what is on the branch under the Story
    file's own name is what attempt 2 wrote — and it echoes what attempt 2 was asked."""
    worktree = answered["detail"]["run"]["worktree_path"]

    rewritten = gates.show(worktree, "HEAD", STORY_1_FILE)

    assert "status: done" in rewritten
    assert "status: blocked" not in rewritten
    assert ANSWER_CLAUSE in rewritten


def test_a_the_story_verified_and_its_commit_guard_found_nothing_left(
    answered: dict[str, Any],
) -> None:
    """The scripted agent committed its own work, so the guard's honest outcome is
    `no changes` — `done`, not a failure (`git_commit.py`'s own rule)."""
    detail = answered["detail"]
    build = next(step for step in detail["steps"] if step["path"] == STORY_1_BUILD)
    guard = next(step for step in detail["steps"] if step["path"] == STORY_1_COMMIT_GUARD)

    assert build["attempts"] == ATTEMPTS_AFTER_A_RESUME
    assert step_status(detail, STORY_1_VERIFY) == "done"
    assert guard["status"] == "done"
    assert guard["reason"] == NO_CHANGES


def test_a_the_trajectory_row_records_the_answer_as_a_human_action(
    answered: dict[str, Any], sessions: Any
) -> None:
    """AD-19: one append-only row per Story that reaches `done`, and SM-1 reads
    `human_actions` to tell an unattended Story from one a person unblocked."""
    run_id = UUID(answered["detail"]["run"]["id"])
    with sessions() as session:
        rows = session.execute(
            text(
                "SELECT human_actions FROM trajectory "
                "WHERE run_id = :run_id AND story_id = :story_id"
            ),
            {"run_id": run_id, "story_id": "1"},
        ).all()

    assert len(rows) == 1, rows
    events = [action["event"] for action in rows[0][0]]
    assert "blocked" in events
    assert "answer" in events


# ── scenario B: spec checkpoint → continue ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def spec_checkpoint(api: httpx.Client, answered: dict[str, Any]) -> dict[str, Any]:
    """The same Run, walked on to story 2's own spec checkpoint."""
    run_id = answered["detail"]["run"]["id"]
    detail = poll_until(
        api,
        run_id,
        lambda detail: step_status(detail, STORY_2_BUILD) == "checkpoint",
        "the Run parking at story 2's spec checkpoint",
    )
    return {"id": run_id, "detail": detail}


def test_b_the_spec_checkpoint_parks_on_the_agent_row_with_continue_offered(
    spec_checkpoint: dict[str, Any],
) -> None:
    detail = spec_checkpoint["detail"]

    assert detail["run"]["status"] == "needs_you"
    assert detail["alert"]["park_kind"] == "checkpoint"
    assert detail["alert"]["row_kind"] == "agent"
    assert "continue" in detail["admitted_signals"]


def test_b_the_planned_story_file_is_readable_through_the_files_endpoint(
    api: httpx.Client, spec_checkpoint: dict[str, Any]
) -> None:
    """UX-DR10's "the planned story file is shown inline" — the screen reads it through
    `GET /runs/{id}/files`, so this is the read that has to work, not a git command."""
    response = api.get(f"{RUNS}/{spec_checkpoint['id']}/files", params={"path": STORY_2_FILE})

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["path"] == STORY_2_FILE
    assert "status: ready-for-dev" in body["content"]
    assert "Create PLAN.md at the repository root." in body["content"]


@pytest.fixture(scope="module")
def continued(api: httpx.Client, spec_checkpoint: dict[str, Any]) -> dict[str, Any]:
    """*Continue* at the spec checkpoint, walked on until story 2's commit guard is done."""
    response = api.post(f"{RUNS}/{spec_checkpoint['id']}/signals", json={"kind": "continue"})
    assert response.status_code == HTTP_OK, response.text
    detail = poll_until(
        api,
        spec_checkpoint["id"],
        lambda detail: step_status(detail, STORY_2_COMMIT_GUARD) == "done",
        "story 2 finishing after the Continue",
    )
    return {"id": spec_checkpoint["id"], "detail": detail, "signalled": response.json()["status"]}


def test_b_continue_re_dispatches_the_approved_plan_without_asking_for_it_again(
    continued: dict[str, Any], gates: Uj3Reads
) -> None:
    """A Continue is the plan already approved, so its prompt carries no halt (6.2). The
    scenario echoes what it was asked into the Story file, so the branch holds the proof."""
    detail = continued["detail"]
    build = next(step for step in detail["steps"] if step["path"] == STORY_2_BUILD)
    assert build["attempts"] == ATTEMPTS_AFTER_A_RESUME

    prompted = gates.show(detail["run"]["worktree_path"], "HEAD", STORY_2_FILE)

    assert "## Prompt" in prompted
    assert HALT_SUFFIX not in prompted
    assert "status: done" in prompted


def test_b_the_gate_record_holds_exactly_one_continue_for_that_row(
    continued: dict[str, Any],
) -> None:
    continues = [
        entry
        for entry in continued["detail"]["gate_record"]
        if entry["event"] == "continue" and entry["path"] == STORY_2_BUILD
    ]

    assert len(continues) == 1
    assert continues[0]["actor"] == "operator"


# ── scenario C: verify failed twice → repair → skip story ────────────────────────────────


@pytest.fixture(scope="module")
def verify_failed(api: httpx.Client, continued: dict[str, Any]) -> dict[str, Any]:
    """The same Run, walked on to story 3's own `verify_failed` park."""
    detail = poll_until(
        api,
        continued["id"],
        lambda detail: (
            detail["run"]["status"] == "needs_you"
            and (detail["alert"] or {}).get("park_kind") == "verify_failed"
        ),
        "the Run parking verify_failed on story 3",
    )
    return {"id": continued["id"], "detail": detail}


def test_c_the_redispatch_saw_the_story_file_at_in_progress_with_the_verify_failure(
    verify_failed: dict[str, Any], gates: Uj3Reads
) -> None:
    """FR-10: a failed `verify` hands the agent its own file back at `in-progress` with what
    failed under `## Verify Failure`. The `fake` harness overwrites that file the moment it
    starts, so the only place it survives is the prepare commit that wrote it."""
    worktree = verify_failed["detail"]["run"]["worktree_path"]

    prepared = gates.commit_matching(worktree, "HEAD", PREPARE_ATTEMPT_2)
    assert prepared, f"no {PREPARE_ATTEMPT_2!r} commit on the branch"
    handed_back = gates.show(worktree, prepared, STORY_3_FILE)

    assert "status: in-progress" in handed_back
    assert "## Verify Failure" in handed_back
    assert QUALITY_GATE in handed_back


def test_c_the_bounded_redispatch_really_ran_the_story_a_second_time(
    verify_failed: dict[str, Any],
) -> None:
    """FR-10's first turn, as stored state: one `redispatch` record from the gate that
    failed, and a `build` row that was dispatched again because of it."""
    detail = verify_failed["detail"]
    build = next(step for step in detail["steps"] if step["path"] == STORY_3_BUILD)
    sent_back = [
        entry
        for entry in detail["gate_record"]
        if entry["event"] == "redispatch" and entry["path"] == STORY_3_VERIFY
    ]

    assert build["attempts"] == ATTEMPTS_AFTER_A_RESUME
    assert build["status"] == "done"
    assert len(sent_back) == 1
    assert sent_back[0]["actor"] == "machine"


def test_c_the_second_failure_parks_the_run_with_the_count_it_gave_up_at(
    verify_failed: dict[str, Any],
) -> None:
    """FR-10's second turn, which is what makes the bound reachable at all: the gate ran
    again after the redispatch, failed again, and the Run stopped where AD-9 says — not on
    the `internal` stall the walk used to reach here (`walk.py::_sent_back`)."""
    detail = verify_failed["detail"]

    assert detail["alert"]["park_kind"] == "verify_failed"
    assert detail["alert"]["reason"] == VERIFY_FAILED
    assert step_status(detail, STORY_3_VERIFY) == "error"
    assert "skip_story" in detail["admitted_signals"]


def test_c_the_gate_file_the_scenario_deleted_is_really_gone_from_the_branch(
    verify_failed: dict[str, Any], gates: Uj3Reads
) -> None:
    """`delete:` (6.8's own schema addition) is what made the gate fail, and the deletion is
    committed — so the repair below is a real edit, not a re-creation of an untracked file."""
    tree = gates.tree(verify_failed["detail"]["run"]["worktree_path"], "HEAD")

    assert GATE_FILE not in tree


@pytest.fixture(scope="module")
def repaired(api: httpx.Client, verify_failed: dict[str, Any]) -> dict[str, Any]:
    """The Operator's inline repair: one `PUT` inside the Run's own spec folder (6.3)."""
    response = api.put(
        f"{RUNS}/{verify_failed['id']}/files", json={"path": GATE_FILE, "content": "1\n"}
    )
    assert response.status_code == HTTP_OK, response.text
    return {"id": verify_failed["id"], "response": response.json()}


def test_c_the_operator_repairs_the_gate_file_inline_and_it_lands_as_one_commit(
    repaired: dict[str, Any], api: httpx.Client, gates: Uj3Reads
) -> None:
    """CAP-3's own success criterion, inside the journey: the save is one commit named in
    the gate record and never attributed to the agent."""
    detail = detail_of(api, repaired["id"])
    edits = [entry for entry in detail["gate_record"] if entry["event"] == "spec_edit"]
    worktree = detail["run"]["worktree_path"]

    assert repaired["response"]["path"] == GATE_FILE
    assert gates.show(worktree, "HEAD", GATE_FILE) == "1\n"
    assert gates.subject(worktree, "HEAD") == "spec: operator edit (orchestrator)"
    assert len(edits) == 1
    assert edits[0]["actor"] == "operator"
    assert edits[0]["text"] == f"edited {GATE_FILE}"


@pytest.fixture(scope="module")
def skipped(api: httpx.Client, repaired: dict[str, Any]) -> dict[str, Any]:
    """*Skip story* at the `verify_failed` stop, walked on until the Run is terminal."""
    response = api.post(f"{RUNS}/{repaired['id']}/signals", json={"kind": "skip_story"})
    assert response.status_code == HTTP_OK, response.text
    detail = poll_until(
        api,
        repaired["id"],
        lambda detail: detail["run"]["status"] in ("done", "failed", "cancelled"),
        "the Run finishing after the skip",
    )
    return {"id": repaired["id"], "detail": detail, "signalled": response.json()["status"]}


def test_c_the_skip_re_runs_the_verify_as_a_re_baseline_and_it_passes(
    skipped: dict[str, Any],
) -> None:
    """The whole point of the re-baseline: the gate is re-run against the tree the skip
    leaves, so the *next* thing on the branch starts from something green."""
    assert skipped["signalled"] == "running"
    assert step_status(skipped["detail"], STORY_3_VERIFY) == "done"


def test_c_the_frames_done_checkpoint_is_skipped_with_the_story(
    skipped: dict[str, Any],
) -> None:
    """The done checkpoint belongs to the frame, so giving up on the Story gives up on it
    too — the `build` row is left alone because it had already finished."""
    detail = skipped["detail"]
    checkpoint = next(step for step in detail["steps"] if step["path"] == STORY_3_CHECKPOINT)

    assert checkpoint["status"] == "skipped"
    assert checkpoint["reason"] == SKIPPED_BY_OPERATOR
    assert step_status(detail, STORY_3_BUILD) == "done"


def test_c_the_commit_guard_commits_the_leftovers_under_the_operators_words(
    skipped: dict[str, Any], gates: Uj3Reads
) -> None:
    """FR-20: a skipped Story still commits whatever is on the tree, under a message that
    says a person gave up on it rather than that the Story was delivered."""
    detail = skipped["detail"]
    worktree = detail["run"]["worktree_path"]

    assert step_status(detail, STORY_3_COMMIT_GUARD) == "done"
    commit = gates.commit_matching(worktree, "HEAD", SKIP_COMMIT_SUBJECT)
    assert commit, f"no {SKIP_COMMIT_SUBJECT!r} commit on the branch"
    assert gates.subject(worktree, commit) == SKIP_COMMIT_SUBJECT
    assert "SHIP_NOTES.md" in gates.tree(worktree, commit)


@pytest.fixture(scope="module")
def journey_done(skipped: dict[str, Any], report: Any, blocked: dict[str, Any]) -> dict[str, Any]:
    print_gate_record(report, "UJ-3 journey", skipped["detail"])
    report(f"[uj3] journey finished in {time.monotonic() - blocked['started_at']:.1f}s")
    return skipped


def test_c_the_run_ends_done_naming_the_story_it_gave_up_on(
    journey_done: dict[str, Any],
) -> None:
    """SPEC CAP-8's own success signal, on the wire: the push and the compare link still run
    and the summary names the skipped Story."""
    detail = journey_done["detail"]

    assert detail["run"]["status"] == "done"
    assert step_status(detail, "push") == "done"
    assert step_status(detail, "link") == "done"
    assert detail["summary"]["skipped"] == ["3"]
    # `pr_link.py` records no compare URL for the fixture's own `file://` origin ("no
    # compare link for this host" is `done` too, by design), so an empty list here is the
    # correct outcome rather than a push that did not happen.
    assert detail["run"]["compare_urls"] == []


def test_c_the_work_of_the_two_stories_that_ran_is_on_the_branch(
    journey_done: dict[str, Any], gates: Uj3Reads
) -> None:
    tree = gates.tree(journey_done["detail"]["run"]["worktree_path"], "HEAD")

    assert "NOTIFY.md" in tree
    assert "PLAN.md" in tree
    assert STORY_1_ARCHIVED in tree
    assert GATE_FILE in tree


# ── scenario D: cancel while parked ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def cancelled(
    api: httpx.Client, gates: Uj3Reads, journey_done: dict[str, Any], report: Any
) -> dict[str, Any]:
    """A second Run, parked `blocked`, then cancelled with the Operator's confirmation.

    Started only once the journey Run is terminal, so this module never holds more than one
    of `MAX_ACTIVE_RUNS`'s global slots (AD-12).
    """
    run_id = start_journey_run(api, gates, "uj3-cancel")
    parked = wait_blocked_on_story_1(api, run_id)
    response = api.post(
        f"{RUNS}/{run_id}/signals", json={"kind": "cancel", "payload": {"confirm": True}}
    )
    assert response.status_code == HTTP_OK, response.text
    detail = detail_of(api, run_id)
    print_gate_record(report, "UJ-3 cancel", detail)
    return {
        "id": run_id,
        "parked": parked,
        "signalled": response.json()["status"],
        "detail": detail,
    }


def test_d_the_parked_run_is_cancelled_and_says_so(cancelled: dict[str, Any]) -> None:
    assert cancelled["parked"]["alert"]["park_kind"] == "blocked"
    assert cancelled["signalled"] == "cancelled"
    assert cancelled["detail"]["run"]["status"] == "cancelled"


def test_d_the_worktree_is_removed_and_the_never_pushed_branch_is_deleted(
    cancelled: dict[str, Any], sessions: Any
) -> None:
    """AD-13's `cancel` effects, on real git: the worktree is gone and so is the branch the
    Run created in the base clone — asked about the branch that was *created*, since a Run
    works on the first free ordinal of the declared name (`templates/branches.py`)."""
    with sessions() as session:
        run = SQLAlchemyRunRepository(session).get(UUID(cancelled["id"]))
    assert run is not None
    (worktree,) = run.worktrees
    assert worktree.created_branch is True
    assert worktree.pushed is False

    base = str(Path(worktree.path).parent.parent / "base")

    assert run_check([base, worktree.path, worktree.branch]), (
        f"worktree/branch not cleaned up: base={base} path={worktree.path} branch={worktree.branch}"
    )


def test_d_a_cancelled_run_refuses_a_second_signal(
    api: httpx.Client, cancelled: dict[str, Any]
) -> None:
    """Cancelling is terminal: nothing this epic built can move the Run afterwards."""
    response = api.post(f"{RUNS}/{cancelled['id']}/signals", json={"kind": "answer"})

    assert response.status_code == HTTP_CONFLICT, response.text
