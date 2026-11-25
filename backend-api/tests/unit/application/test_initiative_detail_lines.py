"""The helpers `initiative_detail_steps` composes a step with (story 6, epic 7)."""

from __future__ import annotations

from orchestrator.application.use_cases.initiative_detail_lines import (
    StepContext,
    at_of,
    auto_files_of,
    is_current,
    latest_run,
    token_of,
)
from orchestrator.application.use_cases.initiative_facts import entry_steps
from orchestrator.application.use_cases.initiative_views import _load, _reading, _row
from tests.unit.application.initiative_read_world import ReadWorld


def context(world: ReadWorld, initiative, **overrides) -> StepContext:  # type: ignore[no-untyped-def]
    loaded = _load(world.ports, initiative)
    reading = _reading(world.ports, loaded)
    values = {
        "loaded": loaded,
        "git": world.git,
        "folder": None,
        "row": _row(world.ports, loaded, reading),
        "reading": reading,
        "prior": None,
        "history_files": None,
    }
    values.update(overrides)
    return StepContext(**values)


def test_the_latest_run_is_the_newest_and_none_for_no_run() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    older = world.run(initiative, minutes=0)
    newer = world.run(initiative, initiative_round=2, minutes=5)

    assert latest_run([older, newer]) is newer
    assert latest_run([]) is None


def test_a_row_is_current_when_it_is_the_conversation_row_the_run_is_on() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.parked_spec(initiative)
    on = world.steps.list_for_run(run.id)[0]
    off = world.row(run, 2, kind="agent", status="done", with_resolved={})
    loaded = _load(world.ports, initiative)

    assert is_current(run, on, loaded)
    assert not is_current(run, off, loaded)


def test_the_neighbours_of_a_step_say_what_it_follows() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    world.parked_spec(initiative)
    ctx = context(world, initiative)
    entry = initiative.sequence.workflows[0]
    listed = entry_steps(initiative.sequence, 0)

    first = at_of(ctx, entry, 0, 1, listed, 1)
    gate = at_of(ctx, entry, 0, 1, listed, 2)
    merge = at_of(ctx, entry, 0, 1, listed, 3)

    assert (first.previous, first.previous_is_gate, first.follows_current) == (None, False, False)
    assert (gate.previous, gate.previous_is_gate, gate.follows_current) == ("intake", False, True)
    assert (merge.previous, merge.previous_is_gate) == ("gate", True)


def test_no_step_follows_the_current_one_when_no_run_is_on_this_workflow() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    entry = initiative.sequence.workflows[0]
    listed = entry_steps(initiative.sequence, 0)

    unstarted = at_of(context(world, initiative), entry, 0, 1, listed, 1)
    world.parked_spec(initiative)
    elsewhere = at_of(context(world, initiative), entry, 1, 1, listed, 2)

    assert (unstarted.previous, unstarted.follows_current) == (None, False)
    assert (elsewhere.previous, elsewhere.follows_current) == ("intake", False)


def test_a_workflow_with_no_history_port_lists_no_files() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.run(initiative, position=2)
    ctx = context(world, initiative)
    build = initiative.sequence.workflows[2]

    assert auto_files_of(ctx, build, run) == []
    assert auto_files_of(ctx, build, None) == []
    assert auto_files_of(ctx, initiative.sequence.workflows[0], run) == []


def test_the_token_of_a_step_reads_the_initiative_cancelled_state() -> None:
    world = ReadWorld()
    live = world.initiative()
    world.run(live)
    gone = world.initiative(slug="gone", cancelled_at=world.clock.now())
    world.run(gone)

    assert token_of(context(world, live), "planned", None) == "QUE"
    assert token_of(context(world, gone), "planned", None) == "CAN"
