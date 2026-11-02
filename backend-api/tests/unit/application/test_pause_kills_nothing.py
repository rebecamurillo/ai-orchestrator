"""Story 2-1: a pause kills nothing. The process groups, worktrees and branches are untouched,
and the outcome carries no cancel plan for the router to act on."""

from __future__ import annotations

from orchestrator.application.use_cases.signals import SignalEffectPorts, handle_signal
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import EPIC_PLAN, a_world, an_attempt
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

BUILD = "stories[0].build"
PGID = 4321


def test_a_pause_with_an_agent_process_running_kills_and_removes_nothing() -> None:
    world = a_world("running", EPIC_PLAN, {BUILD: "running"})
    an_attempt(world, BUILD, pgid=PGID)
    process, git = FakeProcessRunner(), FakeGit()
    ports = SignalEffectPorts(
        signal=world.signal_ports,
        git=git,
        process=process,
        work_dir="/work",
        read_environment=lambda _run_id: None,
    )

    outcome = handle_signal(ports, world.run.id, Signal(kind="pause"))

    assert outcome.cancel_plan is None
    assert outcome.resumed is False
    assert process.called("kill_group") == []
    assert git.called("remove_worktree") == []
    assert git.called("delete_branch") == []
    assert world.attempts_of(BUILD)[0].ended_at is None
    assert world.status_of(BUILD) == "running"
