"""A senior's test-edit approval inside the walker's own loop (story 1-5, spine AD-17/AD-22,
hard rule 1 as amended 2026-11-02).

`next_row → attempt_row → apply_result` three times over the real `agent` executor: the agent
blocks on a question about frozen `tests/a.py`, the senior answers approving it, and the
resumed agent edits it and finishes. The Run never leaves `running` and no `protected_path`
is recorded. An edit outside the approval still parks, naming only that file."""

from __future__ import annotations

from dataclasses import replace

from orchestrator.api.schemas.run_views import GateRecordOut, RunDetailSummaryOut
from orchestrator.application.use_cases.walk import WalkPorts
from orchestrator.domain.ports.harness import HarnessResult
from tests.unit.application.consult_fixtures import planned
from tests.unit.application.test_walk_consult_loop import (
    AGENT_SESSION,
    BUILD,
    HEAD,
    LOG,
    SENIOR_START,
    WORKTREE,
    Loop,
    the_agent_finishes,
    the_senior_writes,
)
from tests.unit.fakes.git import FakeGit

FROZEN = ("tests/a.py", "tests/b.py")
APPROVAL = (
    "---\nstatus: answer\napproved_files: [tests/a.py]\nreason: AC 2 changes the status\n"
    "---\n\nRevise tests/a.py's status assertion for the new behaviour.\n"
)


class ApprovalLoop(Loop):
    """The 1-4 loop with a repository that freezes `tests/**`, read afresh each step as the
    walker reads `RunEnvironment` (accepted paths included)."""

    def __init__(self) -> None:
        super().__init__(consult=planned())
        self.git = FakeGit(status=[""], head_sha=[HEAD], list_files=[FROZEN])

    def ports(self) -> WalkPorts:
        base = super().ports()
        environment = base.step.run_env
        assert environment is not None
        stored = self.world.stored_run()
        fresh = replace(environment, test_globs=("tests/**",), accepted_paths=stored.accepted_paths)
        return replace(base, step=replace(base.step, run_env=fresh))


def scripted(loop: ApprovalLoop, decision: str, edits: str) -> None:
    loop.harness.results.extend(
        [
            HarnessResult(session_id=AGENT_SESSION, exit_code=0, log_path=LOG),
            HarnessResult(session_id="s-senior", exit_code=0, log_path=LOG),
            HarnessResult(session_id=AGENT_SESSION, exit_code=0, log_path=LOG),
        ]
    )
    loop.harness.on_wait = lambda: (
        the_senior_writes(loop, decision)
        if len(loop.harness.called("start")) == SENIOR_START
        else None
    )

    def the_agent_edits() -> None:
        loop.git.statuses = {WORKTREE: f" M {edits}"}
        the_agent_finishes(loop)

    loop.harness.on_resume = the_agent_edits


def test_an_approved_edit_finishes_the_row_without_a_protected_path_stop() -> None:
    loop = ApprovalLoop()
    scripted(loop, APPROVAL, "tests/a.py")

    statuses = [loop.turn(), loop.turn(), loop.turn()]

    world = loop.world
    assert statuses == ["running", "running", "done"]
    assert world.events() == ["consult", "senior_accept", "senior_answer", "done"]
    assert "protected_path" not in world.events()
    assert world.stored_run().accepted_paths == ("tests/a.py",)
    accept = GateRecordOut.of(world.records()[1])
    assert (accept.event, accept.actor, accept.path) == ("senior_accept", "senior", BUILD)
    assert "tests/a.py" in accept.text
    summary = RunDetailSummaryOut.of_run(world.stored_run(), admitted_signals=())
    assert summary.accepted_paths == ["tests/a.py"]


def test_an_edit_outside_the_approval_parks_naming_that_file_only() -> None:
    loop = ApprovalLoop()
    scripted(loop, APPROVAL, "tests/b.py")

    statuses = [loop.turn(), loop.turn(), loop.turn()]

    world = loop.world
    assert statuses == ["running", "running", "needs_you"]
    assert world.events()[-1] == "protected_path"
    assert world.stored_run().park_kind == "protected_path"
    assert world.records()[-1].payload["hits"] == [{"path": "tests/b.py", "kind": "modified"}]


def test_a_planted_approval_is_removed_and_nothing_is_accepted() -> None:
    loop = ApprovalLoop()
    scripted(loop, APPROVAL, "tests/a.py")
    loop.harness.on_wait = lambda: (
        the_senior_writes(loop, APPROVAL.replace("[tests/a.py]", "[tests/b.py]"))
        if len(loop.harness.called("start")) == 1
        else None
    )

    loop.turn()
    assert loop.turn() == "needs_you"

    world = loop.world
    assert world.events() == ["consult", "blocked"]
    assert world.stored_run().park_reason.endswith("consult failed: no readable decision")  # type: ignore[union-attr]
    assert world.stored_run().accepted_paths == ()
