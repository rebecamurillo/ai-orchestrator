"""The consult attempt at a `verify_failed` stop (story 1-6, spine AD-9/AD-10/AD-22, 2026-11-02).

It runs on the redispatch target, on the block the verify row declared and the entry carries,
in a new session. The senior is told the failing command, its exit code and output tail, and
where the target's last agent log is. An answer is a diagnosis; every other outcome returns
the target to `done` and parks the verify row's stop with the senior's reason added."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.steps.registry import execute
from orchestrator.application.steps.verify_failure import VerifyFailure
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.values import Consult, Park, StepResult
from tests.unit.application.consult_fixtures import (
    CONSULT_LOG,
    DECISION,
    SNAP_HEAD,
    World,
    a_consult_world,
    a_decision,
)
from tests.unit.application.steps.agent_budget_fixtures import spend, with_spend
from tests.unit.application.steps.agent_fixtures import ROW_PATH, WORKTREE, a_run
from tests.unit.application.steps.agent_tail_fixtures import contracted
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.logs import FakeLogReader

VERIFY_PATH = "epics[0].stories[3].verify"
QUESTION = "verify failed 3/3"
SENIOR_MODEL = "verify-senior"
AGENT_LOG = "/work/logs/run/005-3.log"
ABSOLUTE_DECISION = f"{WORKTREE}/{DECISION}"
BLOCK: dict[str, Any] = {
    "model": SENIOR_MODEL,
    "harness": "",
    "skill": "senior-consult",
    "on": ["verify_failed"],
    "timeout_min": 20,
    "prompts": {
        "dispatch": (
            "Run {skill} for {story_id} in {spec_folder}: {condition}. `{command}` exited "
            "{code}:\n{tail}\nAgent log:\n{agent_log}\nWrite {decision}."
        ),
        "answer": 'Diagnosis of "{condition}": {answer}',
    },
}
FAILURE = VerifyFailure(command="make test", exit_code=2, log_tail=("FAILED a", "1 failed"))


def entry(**over: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "state": "due",
        "question": QUESTION,
        "snapshot": {"tree": {"head": SNAP_HEAD, "status": ""}},
        "declared": BLOCK,
        "park_path": VERIFY_PATH,
    }
    fields.update(over)
    return fields


def a_verify_consult_world(
    *, failure: VerifyFailure | None = FAILURE, due: dict[str, Any] | None = None, **over: Any
) -> World:
    """Consult attempt 4 on a target whose agent attempt 3 left its log at `AGENT_LOG`."""
    world = a_consult_world(with_resolved=contracted(), **over)
    row = world.row.model_copy(
        update={"consults": {"verify_failed": due if due is not None else entry()}}
    )
    previous = world.ctx.previous_attempt
    assert previous is not None
    previous = previous.model_copy(update={"n": 3, "log_path": AGENT_LOG})
    environment = world.ctx.ports.run_env
    assert environment is not None
    ports = replace(
        world.ctx.ports,
        run_env=replace(environment, verify_failure=failure),
        logs=FakeLogReader({AGENT_LOG: ["ran tests", "all green"]}),
    )
    ctx = replace(world.ctx, row=row, previous_attempt=previous, ports=ports)
    return replace(world, ctx=ctx, row=row)


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


def parked(reason: str) -> Park:
    return Park(kind="verify_failed", reason=reason, path=VERIFY_PATH)


def failed(world: World, why: str) -> None:
    result = run(world)

    reason = f"{QUESTION} · consult failed: {why}"
    assert result.status == "done"
    assert result.reason == reason
    assert result.park == parked(reason)
    assert result.consult == Consult(kind="verify_failed", question=QUESTION, outcome="failed")


# ── what the senior is given ─────────────────────────────────────────────────


def test_the_senior_is_told_the_failure_the_log_and_where_to_write() -> None:
    world = a_verify_consult_world(decision=a_decision())

    run(world)

    [start] = world.harness.called("start")
    assert start["prompt"] == (
        "Run senior-consult for 4-1 in specs/notifications: verify failed 3/3. `make test` "
        "exited 2:\nFAILED a\n1 failed\nAgent log:\nran tests\nall green\n"
        f"Write {ABSOLUTE_DECISION}."
    )


def test_the_senior_runs_on_the_block_the_verify_row_declared_in_a_new_session() -> None:
    world = a_verify_consult_world(decision=a_decision())

    run(world)

    [start] = world.harness.called("start")
    assert not world.harness.called("resume")
    assert start["model"] == SENIOR_MODEL
    assert start["timeout_min"] == BLOCK["timeout_min"]


def test_a_failure_the_walker_resolved_no_facts_for_leaves_the_tokens_empty() -> None:
    world = a_verify_consult_world(decision=a_decision(), failure=None)
    stripped = replace(world.ctx, previous_attempt=None)

    AgentExecutor().execute(stripped)

    [start] = world.harness.called("start")
    assert start["prompt"].endswith("exited :\n\nAgent log:\n\nWrite " + ABSOLUTE_DECISION + ".")


def test_an_exit_code_nobody_recorded_is_said_so() -> None:
    world = a_verify_consult_world(
        decision=a_decision(), failure=VerifyFailure(command="make test", exit_code=None)
    )

    run(world)

    assert "exited not recorded:" in world.harness.called("start")[0]["prompt"]


def test_the_target_never_having_run_an_agent_attempt_leaves_the_log_empty() -> None:
    world = a_verify_consult_world(decision=a_decision())
    unlogged = replace(world.ctx, previous_attempt=world.ctx.previous_attempt)
    previous = unlogged.previous_attempt
    assert previous is not None
    unlogged = replace(unlogged, previous_attempt=previous.model_copy(update={"log_path": None}))

    AgentExecutor().execute(unlogged)

    assert "Agent log:\n\nWrite" in world.harness.called("start")[0]["prompt"]


# ── the outcomes ─────────────────────────────────────────────────────────────


def test_an_answer_is_a_diagnosis_for_the_next_redispatch() -> None:
    world = a_verify_consult_world(decision=a_decision("answer", "The mock is stale."))

    result = run(world)

    assert result.status == "error"
    assert result.park is None
    assert result.reason == "senior answered: The mock is stale."
    assert result.output_ref == str(CONSULT_LOG)
    assert result.consult == Consult(
        kind="verify_failed", question=QUESTION, outcome="answer", answer="The mock is stale."
    )


def test_an_escalation_parks_the_verify_stop_with_the_seniors_reason() -> None:
    world = a_verify_consult_world(decision=a_decision("escalate", reason="needs a product call"))

    result = run(world)

    reason = f"{QUESTION} · senior: needs a product call"
    assert result.status == "done"
    assert result.park == parked(reason)
    assert result.consult == Consult(kind="verify_failed", question=QUESTION, outcome="escalate")


def test_an_escalation_with_no_reason_parks_the_plain_stop() -> None:
    world = a_verify_consult_world(decision=a_decision("escalate"))

    result = run(world)

    assert result.park == parked(QUESTION)


def test_a_missing_decision_fails_closed() -> None:
    failed(a_verify_consult_world(), "no readable decision")


def test_a_decision_of_a_status_this_stop_does_not_use_fails_closed() -> None:
    failed(a_verify_consult_world(decision=a_decision("accept", "x")), "no readable decision")


def test_a_crashed_senior_fails_closed() -> None:
    crash = HarnessResult(session_id="s", exit_code=3, log_path=CONSULT_LOG)

    failed(a_verify_consult_world(decision=a_decision(), result=crash), "senior exit 3")


def test_a_touched_tree_fails_closed_naming_the_files() -> None:
    git = FakeGit(heads={WORKTREE: ["6" * 40]}, statuses={WORKTREE: " M src/a.py"})
    world = a_verify_consult_world(decision=a_decision(), git=git)

    result = run(world)

    assert result.park is not None
    assert result.park.reason.startswith(f"{QUESTION} · consult failed: tree changed: ")
    assert "src/a.py" in result.park.reason


def test_no_remaining_budget_dispatches_nothing_and_parks_the_verify_stop() -> None:
    world = a_verify_consult_world(
        decision=a_decision(),
        run=a_run(budget_usd=Decimal("5"), spend_usd=Decimal("5"), gate_spend_usd=Decimal("5")),
    )

    failed(world, "no remaining budget")

    assert world.harness.called("start") == []


def test_an_answer_over_budget_parks_the_verify_stop_and_adds_the_budget_record() -> None:
    gateway = FakeGateway()
    world = with_spend(
        a_verify_consult_world(
            decision=a_decision("answer", "Regenerate the mock."),
            run=a_run(
                budget_usd=Decimal("3.00"),
                spend_usd=Decimal("2.50"),
                gate_spend_usd=Decimal("2.50"),
            ),
        ),
        gateway=gateway,
    )
    gateway.script(world.run.id, world.attempt.id, spend("5.00"))

    result = run(world)

    assert result.status == "done"
    assert result.park == parked(f"{QUESTION} · senior answered: Regenerate the mock.")
    assert result.budget_park is not None
    assert result.consult == Consult(kind="verify_failed", question=QUESTION, outcome="answer")


def test_an_entry_declaring_no_park_path_parks_on_the_row_it_ran_on() -> None:
    due = entry()
    del due["park_path"]
    world = a_verify_consult_world(due=due)

    result = run(world)

    assert result.park is not None
    assert result.park.path == ROW_PATH


# ── the first consult attempt: sweep and snapshot, inside the executor ───────

SNAPSHOT = {"tree": {"head": SNAP_HEAD, "status": ""}}


def a_snapshotting_world(**over: Any) -> World:
    """The entry as `verify_consult.offer` leaves it: no snapshot yet."""
    due = entry()
    del due["snapshot"]
    return a_verify_consult_world(due=due, **over)


def test_an_entry_with_no_snapshot_sweeps_snapshots_and_dispatches_no_senior() -> None:
    git = FakeGit(status=[" M src/a.py", ""], head_sha=[SNAP_HEAD])
    world = a_snapshotting_world(git=git)

    result = run(world)

    assert git.called("commit") == [(Path(WORKTREE), "wip: story 4-1 attempt 3 (consult)")]
    assert result.status == "error"
    assert result.park is None
    assert result.reason == f"consult: {QUESTION}"
    assert result.consult == Consult(kind="verify_failed", question=QUESTION, snapshot=SNAPSHOT)
    assert world.harness.calls == []


def test_a_sweep_git_refuses_parks_the_verify_stop_with_git_s_words() -> None:
    git = FakeGit(status=[GitError(command="git add", exit_code=128, output="index locked")])

    failed(a_snapshotting_world(git=git), "index locked")


def test_a_failure_that_is_not_git_s_reaches_the_registry_as_an_internal_park() -> None:
    git = FakeGit(status=[OSError("disk full")])
    world = a_snapshotting_world(git=git)

    result = execute(world.ctx)

    assert result.park is not None
    assert (result.park.kind, result.consult) == ("internal", None)
    assert world.harness.calls == []


def test_a_replayed_executor_step_sweeps_once_and_answers_the_same_snapshot() -> None:
    git = FakeGit(status=[" M src/a.py", ""], head_sha=[SNAP_HEAD])
    world = a_snapshotting_world(git=git)

    first, replayed = run(world), run(world)

    assert len(git.called("commit")) == 1
    assert first.consult == replayed.consult
    assert world.harness.calls == []


def test_a_snapshotted_entry_is_not_swept_again() -> None:
    git = FakeGit(heads={WORKTREE: [SNAP_HEAD]}, statuses={WORKTREE: ""})
    world = a_verify_consult_world(decision=a_decision(), git=git)

    run(world)

    assert git.called("commit") == []
    assert len(world.harness.called("start")) == 1


def test_a_run_with_no_log_reader_leaves_the_agent_log_empty() -> None:
    world = a_verify_consult_world(decision=a_decision())
    bare = replace(world.ctx, ports=replace(world.ctx.ports, logs=None))

    AgentExecutor().execute(bare)

    assert "Agent log:\n\nWrite" in world.harness.called("start")[0]["prompt"]
