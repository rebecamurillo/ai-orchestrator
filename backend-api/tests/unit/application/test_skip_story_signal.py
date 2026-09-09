"""`skip_story` through `handle_signal` (6.4, SPEC CAP-4, FR-20; binds AD-9, AD-13).

Until this story the kind was refused `skip_story not available yet` after `validate`
passed — the 4.5 writer implemented every effect, but Epic 4 shipped no surface to reach it
from. `tests/unit/application/test_handle_signal.py`'s pending-gate registry carried that
row and this story removed it; the tests below are the coverage that replaces it, and they
go through `handle_signal` rather than `signal_run` on purpose: the scope gate is the one
thing this story changed about the path, so the assertion has to run past it.

The brief's own first acceptance criterion is transcribed whole in the first test — every
row it names, the commit message, the Run status and the gate record — rather than split
across the six writer tests `test_signal_run.py` already holds for the effect itself.
"""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.signal_effects import SKIPPED_BY_OPERATOR
from orchestrator.application.use_cases.signal_run import SignalOutcome
from orchestrator.application.use_cases.signals import SignalEffectPorts, handle_signal
from orchestrator.domain.errors import Conflict
from orchestrator.domain.statuses import StepStatus
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

#: The brief's own AC1 plan: the second Story frame of `epic@1`, which carries the
#: checkpoint row (`stories[1].after`) the criterion names beside the build.
SYNC = "stories[1].sync"
BUILD = "stories[1].build"
VERIFY = "stories[1].verify"
COMMIT_GUARD = "stories[1].commit-guard"
AFTER = "stories[1].after"

WORK_DIR = "/work"


def parked(park_kind: str, park_path: str, row_status: StepStatus, **rows: StepStatus) -> World:
    """A Run stopped for the Operator on one row, with the rest of the plan as named."""
    statuses: dict[str, StepStatus] = {park_path: row_status}
    statuses.update(rows)
    return a_world(
        "needs_you",
        EPIC_PLAN,
        statuses,
        park_kind=park_kind,
        park_path=park_path,
        park_reason="why it stopped",
    )


def ports_for(world: World) -> SignalEffectPorts:
    """`handle_signal`'s ports. `skip_story` reaches neither git nor a process: its whole
    effect is rows, so the two adapters below are wired only because the dataclass needs
    them, and a call on either would be this story writing outside `signal_run`."""
    return SignalEffectPorts(
        signal=world.signal_ports,
        git=FakeGit(),
        process=FakeProcessRunner(),
        work_dir=WORK_DIR,
        read_environment=lambda _run_id: None,
    )


def skip(world: World) -> SignalOutcome:
    return handle_signal(ports_for(world), world.run.id, Signal(kind="skip_story", payload={}))


def test_skipping_a_blocked_story_applies_every_effect_the_brief_names() -> None:
    """AC1, whole: `sync done, build blocked, verify planned, commit_guard planned, after
    planned` → build and after skipped, verify queued, the commit message re-resolved, the
    Run running, and `skip_story` on the gate record."""
    world = parked("blocked", BUILD, "blocked", **{SYNC: "done"})

    outcome = skip(world)

    assert world.status_of(BUILD) == "skipped"
    assert world.row(BUILD).reason == SKIPPED_BY_OPERATOR
    assert world.status_of(AFTER) == "skipped"
    assert world.row(AFTER).reason == SKIPPED_BY_OPERATOR
    assert world.status_of(VERIFY) == "queued"
    assert world.row(COMMIT_GUARD).with_resolved["message"] == "story 2: skipped by operator"
    assert outcome.run.status == "running"
    assert "skip_story" in world.events()


def test_the_skip_wakes_the_engine_so_the_re_baseline_actually_runs() -> None:
    """The queued `verify` row is only a re-baseline if something walks it: `signal_run`
    tells the engine exactly when the signal moved the Run to `running` (AD-13)."""
    world = parked("blocked", BUILD, "blocked")

    outcome = skip(world)

    assert outcome.resumed
    assert [name for name, _ in world.engine.calls] == ["signal"]


def test_a_frame_whose_verify_was_planned_away_queues_its_commit_row_instead() -> None:
    """AC4: `skipped · no quality_gate_command` is a finished row, so the walk from the
    parked row lands on the frame's own `git.commit` row."""
    world = parked("blocked", BUILD, "blocked", **{VERIFY: "skipped"})

    skip(world)

    assert world.status_of(VERIFY) == "skipped"
    assert world.status_of(COMMIT_GUARD) == "queued"


def test_a_skip_at_a_done_checkpoint_marks_that_row_skipped_and_carries_on() -> None:
    """The brief's own done-checkpoint rule: the build was done and the trajectory already
    written, so the checkpoint row is what the skip consumes — and the Run walks past the
    whole frame to the epic's `push`."""
    world = parked(
        "checkpoint",
        AFTER,
        "checkpoint",
        **{BUILD: "done", VERIFY: "done", COMMIT_GUARD: "done"},
    )

    outcome = skip(world)

    assert world.status_of(AFTER) == "skipped"
    assert world.status_of(COMMIT_GUARD) == "done"
    assert world.status_of("push") == "queued"
    assert outcome.run.status == "running"


def test_a_finished_commit_row_keeps_the_title_it_was_planned_with() -> None:
    """Only a commit that has not run yet can still carry the Operator's words; one that
    already committed the Story is history, not a message to rewrite."""
    world = parked("checkpoint", AFTER, "checkpoint", **{COMMIT_GUARD: "done"})

    skip(world)

    assert world.row(COMMIT_GUARD).with_resolved == {}


def test_a_park_outside_any_story_frame_is_refused_by_the_table_not_by_this_story() -> None:
    """`_has_story_frame` is AD-13's own `extra` for this kind, and it still runs first: the
    refusal names the table, not the scope gate this story widened."""
    world = parked("misconfigured", "push", "error")

    with pytest.raises(Conflict, match="signal skip_story invalid for status needs_you"):
        skip(world)

    assert world.status_of("push") == "error"
    assert world.engine.calls == []
