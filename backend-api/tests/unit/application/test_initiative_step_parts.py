"""The per-step facts of the initiative detail (story 6, epic 7; AC3, AC4, AC5, AC7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from orchestrator.application.use_cases.initiative_step_parts import (
    agent_of,
    conflicts_of,
    forced,
    harness_model,
    park_of,
    step_number,
    timed_files,
    turn_status,
)
from orchestrator.domain.entities.project_package import StepDecl
from orchestrator.domain.ports.git import Change, GitError
from tests.unit.application.initiative_read_world import WORKTREE, ReadWorld
from tests.unit.fakes.git import FakeGit

PRD = "initiatives/snake/PRD.md"
T1 = datetime(2026, 11, 24, 21, 30, tzinfo=UTC)


def decl(**overrides: Any) -> StepDecl:
    values: dict[str, Any] = {
        "id": "ux",
        "kind": "conversation",
        "skill": "s",
        "persona": "personas/ux-designer.md",
        "file": None,
        "writes": (),
    }
    values.update(overrides)
    return StepDecl(**values)


def test_step_number_joins_workflow_and_position() -> None:
    assert step_number(2, 5) == "2.5"


def test_agent_is_the_persona_file_stem_of_a_conversation_step() -> None:
    assert agent_of(decl()) == "ux-designer"
    assert agent_of(decl(persona=None)) is None
    assert agent_of(decl(kind="automatic")) is None


def test_harness_and_model_come_from_the_last_step_session_start() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.run(initiative, inputs={"harness": "codex", "model": "m0"})
    row = world.row(run, 1)
    other = world.row(run, 2)
    first = world.session_start(run, row, 1, harness="claude", model="m1")
    second = world.session_start(run, row, 2, harness="opencode", model="m2")
    elsewhere = world.session_start(run, other, 3, harness="x", model="y")
    senior = world.session_start(run, row, 4, scope="turn", harness="z", model="w")

    records = [first, second, elsewhere, senior]

    assert harness_model(run, row, records) == ("opencode", "m2")
    assert harness_model(run, other, records) == ("x", "y")


def test_harness_and_model_fall_back_to_the_run_inputs() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.run(initiative, inputs={"harness": "codex", "model": "m0"})
    row = world.row(run, 1)
    senior = world.session_start(run, row, 4, scope="run", harness="z", model="w")

    assert harness_model(run, row, [senior]) == ("codex", "m0")
    assert harness_model(run, None, [senior]) == ("codex", "m0")
    assert harness_model(world.run(initiative, initiative_round=2), row, []) == (None, None)
    assert harness_model(None, None, []) == (None, None)


def test_a_run_parked_at_the_row_carries_its_stop() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.run(
        initiative,
        status="needs_you",
        park_kind="merge_conflict",
        park_path="steps[1]",
        park_reason="why",
        park_seq=4,
    )
    here = world.row(run, 1)
    there = world.row(run, 2)

    assert tuple(park_of(run, here)) == (4, "merge_conflict", "why")
    assert tuple(park_of(run, None)) == (4, "merge_conflict", "why")
    assert tuple(park_of(run, there)) == (None, None, None)
    assert tuple(park_of(world.run(initiative, initiative_round=2, status="running"), None)) == (
        None,
        None,
        None,
    )
    assert tuple(park_of(None, None)) == (None, None, None)


def merge_world(
    output: str | None, *, kind: str = "git.merge", park: str = "merge_conflict"
) -> Any:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.run(initiative, status="needs_you", park_kind=park, park_path="steps[1]")
    row = world.row(run, 1, kind=kind)
    world.turn(row, 1, role="agent", output_ref="old\nconflicted paths:\nstale.md")
    attempts = [] if output is None else [world.turn(row, 2, role="agent", output_ref=output)]
    return run, [row], world.attempts.list_for_row(row.id) if attempts else attempts[:0]


def test_the_conflict_files_are_the_listing_of_the_latest_merge_attempt() -> None:
    run, rows, attempts = merge_world("failed\nconflicted paths:\na.md\nb.md")

    assert conflicts_of(run, rows, attempts) == ["a.md", "b.md"]


def test_no_conflict_files_off_a_merge_conflict_stop_or_another_row() -> None:
    run, rows, attempts = merge_world("conflicted paths:\na.md")
    assert run.park_kind == "merge_conflict"
    elsewhere, other_rows, other_attempts = merge_world("conflicted paths:\na.md", kind="agent")
    quiet, quiet_rows, _ = merge_world("conflicted paths:\na.md", park="blocked")
    parked, none_rows, _ = merge_world(None)

    assert conflicts_of(None, rows, attempts) == []
    assert conflicts_of(elsewhere, other_rows, other_attempts) == []
    assert conflicts_of(quiet, quiet_rows, attempts) == []
    assert conflicts_of(parked, [], attempts) == []
    assert conflicts_of(parked, none_rows, []) == []


@pytest.mark.parametrize(
    ("attempt_status", "expected"),
    [
        ("queued", "queued"),
        ("planned", "queued"),
        ("running", "running"),
        ("error", "failed"),
        ("blocked", "failed"),
        ("done", "done"),
        ("checkpoint", "done"),
    ],
)
def test_turn_status(attempt_status: str, expected: str) -> None:
    world = ReadWorld()
    initiative = world.initiative()
    row = world.row(world.run(initiative), 1)

    assert turn_status(world.turn(row, 1, status=attempt_status)) == expected


def test_forced_reads_the_skip_reason() -> None:
    world = ReadWorld()
    run = world.run(world.initiative())

    assert forced(world.row(run, 1, status="skipped", reason="skipped, forced · x"))
    assert not forced(world.row(run, 2, status="skipped", reason="not in this round"))
    assert not forced(world.row(run, 3, status="skipped"))
    assert not forced(world.row(run, 4, status="done", reason="skipped, forced"))
    assert not forced(None)


def by_run_world(git: FakeGit) -> Any:
    world = ReadWorld(git=git)
    initiative = world.initiative()
    first = world.run(initiative, minutes=0, status="done", worktree_path=WORKTREE)
    second = world.run(
        initiative, minutes=10, initiative_round=2, status="running", worktree_path=WORKTREE
    )
    one = world.turn(
        world.row(first, 1), 1, start_sha="a", end_sha="b", ended_at=T1 - timedelta(hours=2)
    )
    two = world.turn(world.row(second, 1), 1, start_sha="c", end_sha="d", ended_at=T1)
    return first, second, [(first, [one]), (second, [two])]


def test_each_path_takes_the_latest_run_whose_range_lists_it() -> None:
    changes = (Change(PRD, "added"), Change("initiatives/snake/UX.md", "added"))
    git = FakeGit(changes={WORKTREE: changes})
    _, second, by_run = by_run_world(git)

    files = timed_files(
        by_run, git, "initiatives/snake/", draft=True, prior=T1 - timedelta(hours=1)
    )

    assert [(f.path, f.run_id, f.time, f.changed, f.draft) for f in files] == [
        (PRD, second.id, T1, True, True),
        ("initiatives/snake/UX.md", second.id, T1, True, True),
    ]
    assert len(git.called("diff_changes")) == len(by_run)


def test_a_file_changed_before_the_previous_view_is_not_changed() -> None:
    git = FakeGit(changes={WORKTREE: (Change(PRD, "added"),)})
    _, _, by_run = by_run_world(git)

    (file,) = timed_files(by_run, git, "initiatives/snake/", draft=False, prior=T1)

    assert (file.changed, file.time) == (False, T1)


def test_with_no_previous_view_nothing_reads_changed() -> None:
    git = FakeGit(changes={WORKTREE: (Change(PRD, "added"),)})
    _, _, by_run = by_run_world(git)

    (file,) = timed_files(by_run, git, "initiatives/snake/", draft=False, prior=None)

    assert file.changed is False


def test_a_turn_that_never_ended_has_no_time_and_is_not_changed() -> None:
    git = FakeGit(changes={WORKTREE: (Change(PRD, "added"),)})
    world = ReadWorld(git=git)
    run = world.run(world.initiative(), worktree_path=WORKTREE)
    turn = world.turn(world.row(run, 1), 1, start_sha="a", end_sha="b", ended_at=None)

    (file,) = timed_files([(run, [turn])], git, "initiatives/snake/", draft=True, prior=T1)

    assert (file.time, file.changed) == (None, False)


def test_paths_outside_the_folder_and_failed_ranges_are_left_out() -> None:
    git = FakeGit(
        diff_changes=[
            (Change("elsewhere/x.md", "added"),),
            GitError(command="git diff", exit_code=128, output="bad"),
        ]
    )
    _, _, by_run = by_run_world(git)

    assert timed_files(by_run, git, "initiatives/snake/", draft=True, prior=T1) == []
    assert timed_files(by_run, git, None, draft=True, prior=T1) == []
