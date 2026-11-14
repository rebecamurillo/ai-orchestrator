"""The consult attempt (story 1-4, spine AD-21/AD-22, 2026-11-02): a new senior session that
writes a decision file, read through the Workspace port. An answer goes back for delivery;
every other outcome parks the original `blocked` stop, with the senior's reason when it gave
one."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.domain.ports.git import Change, GitError
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.values import Consult, Park, StepResult
from tests.unit.application.consult_fixtures import (
    AGENT_SESSION,
    CONDITION,
    CONSULT_LOG,
    CONSULT_SKILL,
    DECISION,
    QUESTION,
    SENIOR_MODEL,
    SNAP_HEAD,
    World,
    a_consult_world,
    a_decision,
    consulting,
    due_entry,
    planned,
)
from tests.unit.application.steps.agent_budget_fixtures import spend, with_spend
from tests.unit.application.steps.agent_fixtures import (
    HARNESS_NAME,
    ROW_PATH,
    SPEC_FOLDER,
    STORY_ID,
    WORKTREE,
    a_run,
)
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.fakes.tracer import FakeTracer

ABSOLUTE_DECISION = f"{WORKTREE}/{DECISION}"
WRITES = {"mark_started", "update", "mark_finished"}


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


def writes(world: World) -> list[str]:
    return [call[0] for call in world.attempts.calls if call[0] in WRITES]


def parked(reason: str) -> Park:
    return Park(kind="blocked", reason=reason, path=ROW_PATH)


def failed(world: World, why: str) -> None:
    result = run(world)

    reason = f"{QUESTION} · consult failed: {why}"
    assert result.status == "blocked"
    assert result.reason == reason
    assert result.park == parked(reason)
    assert result.consult == Consult(kind="blocked", question=QUESTION, outcome="failed")


# ── an answer ────────────────────────────────────────────────────────────────


def test_an_answer_goes_back_for_delivery_with_its_body() -> None:
    world = a_consult_world(decision=a_decision("answer", "Use the v2 route.\nThen stop."))

    result = run(world)

    assert result.status == "error"
    assert result.park is None
    assert result.reason == "senior answered: Use the v2 route."
    assert result.output_ref == str(CONSULT_LOG)
    assert result.consult == Consult(
        kind="blocked",
        question=QUESTION,
        outcome="answer",
        answer="Use the v2 route.\nThen stop.",
    )


def test_the_senior_runs_in_a_new_session_on_its_own_model() -> None:
    world = a_consult_world(decision=a_decision())

    run(world)

    assert not world.harness.called("resume")
    [start] = world.harness.called("start")
    assert start["session_id"] != AGENT_SESSION
    assert start["model"] == SENIOR_MODEL
    assert start["cwd"] == Path(WORKTREE)
    assert start["timeout_min"] == planned()["timeout_min"]
    assert start["add_dirs"] == ()
    assert start["prompt"] == (
        f"Run {CONSULT_SKILL} for story {STORY_ID} in {SPEC_FOLDER}. "
        f"The agent asks: {QUESTION}. Write {ABSOLUTE_DECISION}."
    )


def test_the_decision_folder_ignores_itself() -> None:
    world = a_consult_world(decision=a_decision())

    run(world)

    assert world.workspace.read(".orchestrator/.gitignore") == "*\n"


def test_the_consult_attempt_is_written_with_its_role_in_three_units_of_work() -> None:
    world = a_consult_world(decision=a_decision())

    run(world)

    stored = world.attempts.get(world.attempt.id)
    assert stored is not None
    assert stored.role == "consult"
    assert stored.harness == HARNESS_NAME
    assert stored.model == SENIOR_MODEL
    assert stored.start_sha is None
    assert stored.frozen_test_files is None
    assert stored.pgid == world.harness.pgid
    assert stored.session_id == "s-senior"
    assert stored.exit_code == 0
    assert stored.log_path == str(CONSULT_LOG)
    assert (stored.tokens_in, stored.tokens_out) == (10, 5)
    assert writes(world) == ["mark_started", "update", "mark_finished"]


def test_the_senior_runs_inside_the_attempt_span() -> None:
    tracer = FakeTracer()
    world = a_consult_world(decision=a_decision(), tracer=tracer)

    run(world)

    [start] = world.harness.called("start")
    assert start["env"]["TRACEPARENT"]
    assert world.harness_env.calls[0]["attempt"].role == "consult"


def test_the_senior_may_run_on_another_harness() -> None:
    senior = FakeHarness(name="codex")
    senior.results.append(HarnessResult(session_id="x", exit_code=0, log_path=CONSULT_LOG))
    world = a_consult_world(
        decision=a_decision(),
        with_resolved=consulting(consult=planned(harness="codex")),
        harnesses={HARNESS_NAME: FakeHarness(), "codex": senior},
    )

    result = run(world)

    assert result.consult is not None
    assert result.consult.outcome == "answer"
    assert senior.called("start")
    stored = world.attempts.get(world.attempt.id)
    assert stored is not None
    assert stored.harness == "codex"


def test_a_workdir_row_runs_the_senior_in_the_member_with_the_hub_reachable() -> None:
    member = f"{WORKTREE}/repos/member"
    git = FakeGit(
        heads={member: [SNAP_HEAD], WORKTREE: ["9" * 40]},
        statuses={member: "", WORKTREE: ""},
    )
    entry = due_entry(
        snapshot={
            "tree": {"head": SNAP_HEAD, "status": ""},
            "root": {"head": "9" * 40, "status": ""},
        }
    )
    world = a_consult_world(
        decision=a_decision(),
        git=git,
        entry=entry,
        with_resolved=consulting(workdir="repos/member"),
    )

    result = run(world)

    assert result.consult is not None
    assert result.consult.outcome == "answer"
    [start] = world.harness.called("start")
    assert start["cwd"] == Path(member)
    assert start["add_dirs"] == (Path(WORKTREE),)
    assert f"{WORKTREE}/{SPEC_FOLDER}" in start["prompt"]
    assert f"{member}/{DECISION}" in start["prompt"]


# ── an escalation ────────────────────────────────────────────────────────────


def test_an_escalation_parks_the_original_stop_with_the_seniors_reason() -> None:
    world = a_consult_world(decision=a_decision("escalate", "", reason="a product decision"))

    result = run(world)

    reason = f"{QUESTION} · senior: a product decision"
    assert result.status == "blocked"
    assert result.park == parked(reason)
    assert result.consult == Consult(kind="blocked", question=QUESTION, outcome="escalate")


def test_an_escalation_without_a_reason_parks_the_question_alone() -> None:
    world = a_consult_world(decision=a_decision("escalate", ""))

    result = run(world)

    assert result.park == parked(QUESTION)


# ── fail closed ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "decision",
    [
        None,
        "no frontmatter\n",
        a_decision("perhaps"),
        a_decision("accept", "tests/a.py"),
        a_decision("answer", ""),
    ],
    ids=["absent", "no frontmatter", "unknown status", "accept", "empty answer"],
)
def test_no_readable_decision_fails_closed(decision: str | None) -> None:
    failed(a_consult_world(decision=decision), "no readable decision")


@pytest.mark.parametrize(
    ("result", "why"),
    [
        (HarnessResult(session_id="x", exit_code=2, log_path=CONSULT_LOG), "senior exit 2"),
        (
            HarnessResult(session_id="x", exit_code=None, log_path=CONSULT_LOG),
            "senior exit not recorded",
        ),
        (
            HarnessResult(session_id="x", exit_code=None, log_path=CONSULT_LOG, stalled=True),
            "senior stalled: no activity for 30 min",
        ),
        (
            HarnessResult(session_id="x", exit_code=None, log_path=CONSULT_LOG, timed_out=True),
            "senior timeout after 20 min",
        ),
    ],
    ids=["exit", "killed", "stall", "timeout"],
)
def test_a_senior_crash_fails_closed_naming_the_exit_or_the_limit(
    result: HarnessResult, why: str
) -> None:
    failed(a_consult_world(decision=a_decision(), result=result), why)


def test_no_remaining_budget_dispatches_nothing() -> None:
    world = a_consult_world(
        run=a_run(
            budget_usd=Decimal("5.00"), spend_usd=Decimal("5.00"), gate_spend_usd=Decimal("5.00")
        )
    )

    failed(world, "no remaining budget")
    assert world.harness.calls == []
    assert writes(world) == []


def test_an_unknown_harness_fails_closed() -> None:
    world = a_consult_world(with_resolved=consulting(consult=planned(harness="nope")))

    failed(world, "unknown harness nope")
    assert world.harness.calls == []


def test_a_moved_head_fails_closed_naming_the_files() -> None:
    git = FakeGit(
        heads={WORKTREE: ["6" * 40]},
        statuses={WORKTREE: ""},
        diff_changes=[(Change(path="src/app.py", kind="modified"),)],
    )

    failed(a_consult_world(decision=a_decision(), git=git), "tree changed: src/app.py")


def test_a_changed_status_fails_closed_naming_the_files() -> None:
    git = FakeGit(heads={WORKTREE: [SNAP_HEAD]}, statuses={WORKTREE: "?? notes.md"})

    failed(a_consult_world(decision=a_decision(), git=git), "tree changed: notes.md")


def test_a_moved_head_with_no_named_file_still_fails_closed() -> None:
    git = FakeGit(heads={WORKTREE: ["6" * 40]}, statuses={WORKTREE: ""}, diff_changes=[()])

    failed(a_consult_world(decision=a_decision(), git=git), "tree changed: HEAD")


def test_a_missing_snapshot_fails_closed() -> None:
    world = a_consult_world(decision=a_decision(), entry=due_entry(snapshot={}))

    failed(world, "tree changed: no snapshot")


def test_a_git_error_fails_closed_with_gits_words() -> None:
    refused = GitError(command="git status", exit_code=128, output="not a git repository")
    git = FakeGit(heads={WORKTREE: [SNAP_HEAD]}, status=[refused])

    failed(a_consult_world(decision=a_decision(), git=git), "not a git repository")


def test_a_harness_error_fails_closed_and_names_it() -> None:
    world = a_consult_world(decision=a_decision())

    def boom(**_: Any) -> None:
        raise RuntimeError("cli missing")

    world.harness.start = boom  # type: ignore[method-assign]

    failed(world, "RuntimeError: cli missing")


def test_a_lost_pgid_write_kills_the_senior_and_fails_closed() -> None:
    world = a_consult_world(decision=a_decision(), writes_failing_on=2)

    result = run(world)

    assert result.park is not None
    assert "consult failed: WriteFailed" in result.park.reason
    assert {"method": "kill_group", "pgid": world.harness.pgid} in world.process.calls


def test_a_consult_attempt_with_no_due_entry_fails_closed() -> None:
    world = a_consult_world(decision=a_decision(), entry={"state": "answer"})

    result = run(world)

    assert result.status == "blocked"
    assert result.park is not None
    assert result.park.reason.endswith("consult failed: no consult due")
    assert world.harness.calls == []


# ── the orphan of a dead backend ─────────────────────────────────────────────


def test_an_orphaned_senior_is_killed_before_anything_else() -> None:
    process = FakeProcessRunner()
    world = a_consult_world(
        decision=a_decision(),
        entry=due_entry(orphan_pgid=777),
        process=process,
        run=a_run(
            budget_usd=Decimal("1.00"), spend_usd=Decimal("1.00"), gate_spend_usd=Decimal("1.00")
        ),
    )

    run(world)

    assert process.calls[0] == {"method": "kill_group", "pgid": 777}
    assert world.harness.calls == []


# ── the consult's own spend ──────────────────────────────────────────────────


def a_priced_world(decision: str, usd: str) -> World:
    gateway = FakeGateway()
    world = with_spend(
        a_consult_world(
            decision=decision,
            run=a_run(
                budget_usd=Decimal("3.00"),
                spend_usd=Decimal("2.50"),
                gate_spend_usd=Decimal("2.50"),
            ),
        ),
        gateway=gateway,
    )
    gateway.script(world.run.id, world.attempt.id, spend(usd))
    return world


def test_an_answer_that_exhausts_the_budget_parks_with_the_budget_on_top() -> None:
    world = a_priced_world(a_decision("answer", "Use the v2 route.\nmore"), "5.00")

    result = run(world)

    reason = f"{QUESTION} · senior answered: Use the v2 route."
    assert result.status == "blocked"
    assert result.park == parked(reason)
    assert result.budget_park is not None
    assert result.budget_park.kind == "budget"
    assert result.consult is not None
    assert result.consult.outcome == "answer"


def test_an_escalation_over_budget_keeps_its_reason_and_gets_the_budget_record() -> None:
    world = a_priced_world(a_decision("escalate", "", reason="r"), "5.00")

    result = run(world)

    assert result.park == parked(f"{QUESTION} · senior: r")
    assert result.budget_park is not None


def test_an_answer_within_budget_goes_back() -> None:
    world = a_priced_world(a_decision(), "0.10")

    result = run(world)

    assert result.park is None
    assert result.consult is not None
    assert result.consult.outcome == "answer"


def test_the_condition_is_the_question_the_offer_recorded() -> None:
    assert CONDITION in QUESTION
