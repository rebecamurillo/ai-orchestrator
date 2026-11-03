"""A senior's diff review of a `protected_path` hit inside the walker's own loop (story 1-8,
spine AD-17/AD-22, hard rule 1 as amended 2026-11-02).

`next_row → attempt_row → apply_result` over the real `agent` executor: the implementer edits
frozen `tests/a.py` and finishes, the senior reads the diff and accepts, and the next attempt
re-runs the tail over the implementer's own range with no dispatch. The Run never leaves
`running` and no `protected_path` is recorded. An escalation parks with the hits, and the
Operator's `continue` resumes through the same re-check. A later attempt dispatches."""

from __future__ import annotations

from orchestrator.api.schemas.run_views import GateRecordOut, RunDetailSummaryOut
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.values import Signal
from tests.unit.application.consult_fixtures import planned
from tests.unit.application.test_consult_approval_loop import FROZEN, ApprovalLoop
from tests.unit.application.test_walk_consult_loop import (
    AGENT_SESSION,
    BUILD,
    HEAD,
    LOG,
    SENIOR_START,
    WORKTREE,
    signal_ports,
    the_agent_finishes,
    the_senior_writes,
)
from tests.unit.fakes.git import FakeGit

ACCEPT = (
    "---\nstatus: accept\napproved_files: [tests/a.py]\n"
    "reason: AC 2 changes the status the test pins\n---\n"
)
ESCALATE = "---\nstatus: escalate\nreason: the story does not change this test\n---\n"
DIFF = "@@ -1 +1 @@\n-assert status == 1\n+assert status == 2\n"
DIFF_FILE = ".orchestrator/consult/001-2.diff"
PLANNED = "stories[0].plan"


class ReviewLoop(ApprovalLoop):
    """1-5's loop, on a row that also consults at a `protected_path` stop, in a frame whose
    earlier row already recorded the frozen test set (AD-17 freezes the frame's first start)."""

    def __init__(self) -> None:
        super().__init__()
        build = self.world.row(BUILD)
        consult = planned(on=["blocked", "protected_path"])
        self.world.ports.steps.update(
            build.model_copy(update={"with_resolved": {**build.with_resolved, "consult": consult}})
        )
        earlier = build.model_copy(
            update={"id": new_id(), "seq": 0, "path": PLANNED, "label": PLANNED, "status": "done"}
        )
        self.world.ports.steps.add_many([earlier])
        self.world.ports.attempts.add(
            Attempt(
                id=new_id(),
                run_id=self.world.run.id,
                step_run_id=earlier.id,
                n=1,
                status="done",
                start_sha=HEAD,
                end_sha=HEAD,
                frozen_test_files=FROZEN,
            )
        )
        self.git = FakeGit(status=[""], head_sha=[HEAD], list_files=[FROZEN], diff=[DIFF])
        self.read_diff: list[str | None] = []


def scripted(loop: ReviewLoop, decision: str) -> None:
    """The implementer edits frozen `tests/a.py` and finishes; the senior then decides."""
    loop.harness.results.extend(
        [
            HarnessResult(session_id=AGENT_SESSION, exit_code=0, log_path=LOG),
            HarnessResult(session_id="s-senior", exit_code=0, log_path=LOG),
        ]
    )

    def on_wait() -> None:
        if len(loop.harness.called("start")) == SENIOR_START:
            loop.read_diff.append(loop.workspace.read(DIFF_FILE))
            the_senior_writes(loop, decision)
            return
        loop.git.statuses = {WORKTREE: " M tests/a.py"}
        the_agent_finishes(loop)

    loop.harness.on_wait = on_wait


def a_review_loop(decision: str) -> ReviewLoop:
    loop = ReviewLoop()
    scripted(loop, decision)
    return loop


def test_an_accepted_edit_finishes_the_row_without_a_protected_path_stop() -> None:
    loop = a_review_loop(ACCEPT)

    statuses = [loop.turn(), loop.turn(), loop.turn()]

    world = loop.world
    assert statuses == ["running", "running", "done"]
    assert world.events() == ["consult", "senior_accept", "done"]
    assert "protected_path" not in world.events()
    assert len(loop.harness.called("start")) == SENIOR_START
    assert loop.harness.called("resume") == []
    assert world.stored_run().accepted_paths == ("tests/a.py",)
    accept = GateRecordOut.of(world.records()[1])
    assert (accept.event, accept.actor, accept.path) == ("senior_accept", "senior", BUILD)
    assert "tests/a.py" in accept.text
    summary = RunDetailSummaryOut.of_run(world.stored_run(), admitted_signals=())
    assert summary.accepted_paths == ["tests/a.py"]
    roles = [(a.n, a.role) for a in world.attempts_of(BUILD)]
    assert roles == [(1, "agent"), (2, "consult"), (3, "agent")]


def test_the_senior_read_the_implementers_real_diff() -> None:
    loop = a_review_loop(ACCEPT)

    loop.turn()
    loop.turn()

    assert loop.read_diff == [f"### tests/a.py\n{DIFF}"]
    [(_, from_sha, path)] = loop.git.called("diff")
    assert path == "tests/a.py"
    assert from_sha == loop.world.attempts_of(BUILD)[0].start_sha


def test_an_escalation_parks_with_the_hits_and_the_operators_continue_resumes() -> None:
    loop = a_review_loop(ESCALATE)
    loop.turn()

    assert loop.turn() == "needs_you"

    world = loop.world
    assert world.events() == ["consult", "protected_path"]
    run = world.stored_run()
    assert run.park_kind == "protected_path"
    assert run.park_reason is not None
    assert run.park_reason.endswith(" · senior: the story does not change this test")
    assert world.records()[-1].payload["hits"] == [{"path": "tests/a.py", "kind": "modified"}]
    signal_run(
        signal_ports(world),
        world.run.id,
        Signal(kind="continue", payload={"files": ["tests/a.py"]}),
    )
    assert loop.turn("continue") == "done"
    assert len(loop.harness.called("start")) == SENIOR_START
    assert world.stored_run().accepted_paths == ("tests/a.py",)


def test_an_attempt_after_the_re_check_dispatches_and_the_accept_is_not_re_applied() -> None:
    loop = a_review_loop(ACCEPT)
    first = loop.harness.on_wait

    def the_implementer_is_unfinished() -> None:
        assert first is not None
        first()
        if len(loop.harness.called("start")) == 1:
            the_agent_finishes(loop, "in-progress")

    loop.harness.on_wait = the_implementer_is_unfinished
    loop.harness.results.append(HarnessResult(session_id=AGENT_SESSION, exit_code=0, log_path=LOG))
    loop.harness.on_resume = lambda: the_agent_finishes(loop)

    statuses = [loop.turn(), loop.turn(), loop.turn(), loop.turn()]

    world = loop.world
    assert statuses == ["running", "running", "running", "done"]
    assert world.events().count("senior_accept") == 1
    calls = len(loop.harness.called("start")) + len(loop.harness.called("resume"))
    assert calls == SENIOR_START + 1
    assert [a.role for a in world.attempts_of(BUILD)] == ["agent", "consult", "agent", "agent"]
