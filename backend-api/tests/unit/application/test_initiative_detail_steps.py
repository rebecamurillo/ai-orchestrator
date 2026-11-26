"""The initiative detail's steps, turns and files (story 4, epic 7; AD-36): AC5-AC7."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.use_cases.initiative_detail_steps import GATE_ROLE
from orchestrator.application.use_cases.initiative_views import initiative_detail
from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.ports.git import Change, GitError
from tests.unit.application.initiative_read_world import WORKTREE, ReadWorld
from tests.unit.fakes.git import FakeGit

PRD = "initiatives/snake/PRD.md"
STORY = "initiatives/snake/STORY.md"


def detail_step(world: ReadWorld, initiative: Initiative, workflow: int, step: int) -> Any:
    return initiative_detail(world.ports, initiative.id).workflows[workflow].steps[step]


def test_a_parked_conversation_waits_for_her_with_its_turns_in_order() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.parked_spec(initiative, turns=2, park_reason="step not closed · no file")

    detail = initiative_detail(world.ports, initiative.id)

    talk = detail.workflows[0].steps[0]
    assert talk.status == "waiting for her"
    assert [(t.n, t.message, t.reply, t.run_id, t.round) for t in talk.turns] == [
        (1, "message 1", "reply 1", run.id, 1),
        (2, "message 2", "reply 2", run.id, 1),
    ]
    assert detail.park_seq == run.park_seq
    assert detail.row.status == "waiting for her"
    assert detail.workflows[0].run_id == run.id
    assert detail.workflows[0].status == "needs_you"
    assert talk.persona == "analyst"
    assert [s.id for s in detail.workflows[0].steps] == ["intake", "gate", "merge"]


def test_a_conversation_waiting_on_her_turn_reads_running() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    world.parked_spec(initiative, turns=2)

    assert detail_step(world, initiative, 0, 0).status == "running"


def test_turns_run_round_one_then_round_two_each_in_order() -> None:
    world = ReadWorld()
    initiative = world.initiative(round=2)
    first = world.run(initiative, minutes=0, status="done")
    second = world.run(initiative, minutes=10, initiative_round=2, status="running")
    first_row = world.row(first, 1, status="done")
    second_row = world.row(second, 1, status="running")
    world.turn(second_row, 2)
    world.turn(first_row, 2)
    world.turn(second_row, 1)
    world.turn(first_row, 1)

    talk = detail_step(world, initiative, 0, 0)

    assert [(t.round, t.n) for t in talk.turns] == [(1, 1), (1, 2), (2, 1), (2, 2)]
    assert talk.status == "running"


@pytest.mark.parametrize(
    ("row_status", "expected"),
    [
        ("done", "done"),
        ("skipped", "skipped"),
        ("queued", "running"),
        ("running", "running"),
        ("error", "failed"),
        ("blocked", "failed"),
        ("planned", "planned"),
    ],
)
def test_a_conversation_row_status_maps_to_the_step_status(row_status: str, expected: str) -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.run(initiative, status="done")
    world.row(run, 1, status=row_status)

    assert detail_step(world, initiative, 0, 0).status == expected


def test_a_row_of_another_step_is_not_this_steps() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.run(initiative, status="running")
    other = world.row(run, 1, status="running", with_resolved={"step": "elsewhere"})
    world.turn(other, 1)

    talk = detail_step(world, initiative, 0, 0)

    assert (talk.status, talk.turns, talk.files, talk.line) == ("planned", [], [], "")


def test_the_step_word_maps_through_the_status_map_while_the_run_runs() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.run(initiative, status="running", worktree_path=WORKTREE)
    world.row(
        run, 1, status="running", with_resolved={"step": "intake", "expect": {"files": [STORY]}}
    )
    world.files[STORY] = "---\nstatus: blocked\n---\n"

    assert detail_step(world, initiative, 0, 0).status == "waiting for her"

    world.files[STORY] = "---\nstatus: other\n---\n"

    assert detail_step(world, initiative, 0, 0).status == "running"


def test_the_gate_reads_its_spec_gate_row() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.parked_spec(initiative, turns=1, park_reason="step not closed · x")
    world.row(run, 2, kind="agent", role=GATE_ROLE, status="blocked", reason="two open questions")

    gate = detail_step(world, initiative, 0, 1)

    assert (gate.id, gate.kind, gate.status, gate.line) == (
        "gate",
        "automatic",
        "failed",
        "two open questions",
    )
    assert (gate.turns, gate.files) == ([], [])


def test_a_gate_with_no_row_is_planned() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    world.run(initiative)

    assert detail_step(world, initiative, 0, 1).status == "planned"


def test_the_merge_step_follows_its_own_latest_run() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    assert detail_step(world, initiative, 0, 2).status == "planned"
    # Revised by story 6 of epic 7 (2026-11-22): the steps strip reads a planned step after
    # the gate as `starts after the gate passes`; it pinned `""` before.
    assert detail_step(world, initiative, 0, 2).line == "starts after the gate passes"

    run = world.run(initiative, position=1, status="needs_you", park_reason="merge it")

    merge = detail_step(world, initiative, 0, 2)
    assert (merge.id, merge.status, merge.line) == ("merge", "waiting for her", "merge it")
    assert (merge.persona, merge.skill, merge.file) == (None, None, None)
    assert run.status == "needs_you"


@pytest.mark.parametrize(
    ("run_status", "expected"),
    [("queued", "running"), ("done", "done"), ("failed", "failed"), ("cancelled", "failed")],
)
def test_the_merge_step_status_follows_the_run_status(run_status: str, expected: str) -> None:
    world = ReadWorld()
    initiative = world.initiative()
    world.run(initiative, position=1, status=run_status)

    assert detail_step(world, initiative, 0, 2).status == expected


def seeded_files(world: ReadWorld, initiative: Initiative, **run: Any) -> Any:
    run_ = world.run(initiative, **{"status": "running", "worktree_path": WORKTREE, **run})
    row = world.row(run_, 1, status="running")
    world.turn(row, 1, start_sha="aaa", end_sha="bbb")
    world.turn(row, 2, start_sha="ccc", end_sha="ddd")
    return run_


def test_files_are_the_step_folder_changes_of_the_turn_range_as_drafts() -> None:
    changes = (Change(PRD, "added"), Change("README.md", "modified"))
    world = ReadWorld(git=FakeGit(changes={WORKTREE: changes}))
    initiative = world.initiative()
    seeded_files(world, initiative)

    talk = detail_step(world, initiative, 0, 0)

    assert [(f.path, f.draft) for f in talk.files] == [(PRD, True)]
    (call,) = world.git.called("diff_changes")
    assert call[1:] == ("aaa", "ddd")


def test_files_of_a_done_step_are_not_drafts_and_repeat_once() -> None:
    changes = (Change(PRD, "added"), Change(PRD, "modified"))
    world = ReadWorld(git=FakeGit(changes={WORKTREE: changes}))
    initiative = world.initiative()
    run = world.run(initiative, status="done", worktree_path=WORKTREE)
    row = world.row(run, 1, status="done")
    world.turn(row, 1, start_sha="aaa", end_sha="bbb")

    assert [(f.path, f.draft) for f in detail_step(world, initiative, 0, 0).files] == [(PRD, False)]


@pytest.mark.parametrize(
    "run",
    [{"worktrees_removed": True}, {"worktree_path": None}],
)
def test_a_run_without_a_live_worktree_adds_no_files(run: dict[str, Any]) -> None:
    git = FakeGit(changes={WORKTREE: (Change(PRD, "added"),)})
    world = ReadWorld(git=git)
    initiative = world.initiative()
    seeded_files(world, initiative, **run)

    assert detail_step(world, initiative, 0, 0).files == []
    assert git.called("diff_changes") == []


def test_a_range_missing_an_end_adds_no_files() -> None:
    git = FakeGit(changes={WORKTREE: (Change(PRD, "added"),)})
    world = ReadWorld(git=git)
    initiative = world.initiative()
    run = world.run(initiative, status="running", worktree_path=WORKTREE)
    row = world.row(run, 1, status="running")
    world.turn(row, 1, start_sha="aaa", end_sha=None)

    assert detail_step(world, initiative, 0, 0).files == []
    assert git.called("diff_changes") == []


def test_a_git_error_adds_no_files() -> None:
    world = ReadWorld(
        git=FakeGit(diff_changes=[GitError(command="git diff", exit_code=128, output="bad object")])
    )
    initiative = world.initiative()
    seeded_files(world, initiative)

    assert detail_step(world, initiative, 0, 0).files == []


def test_without_a_hub_repository_there_is_no_folder_to_filter_by() -> None:
    git = FakeGit(changes={WORKTREE: (Change(PRD, "added"),)})
    world = ReadWorld(git=git)
    initiative = world.initiative()
    seeded_files(world, initiative)
    del world.repositories.repositories[world.hub.id]

    assert detail_step(world, initiative, 0, 0).files == []
    assert git.called("diff_changes") == []


def test_each_run_is_listed_with_its_ad36_round_and_position() -> None:
    # a Run's `round` and `position` are its AD-36 keys, not the shown workflow's number, which
    # the spec and merge Runs share (epic 7 story 4, release review 2026-11-26)
    world = ReadWorld()
    initiative = world.initiative()
    world.run(initiative, position=0, minutes=0)
    world.run(initiative, position=1, minutes=1)
    third = world.run(initiative, position=2, minutes=2, initiative_round=2)

    runs = initiative_detail(world.ports, initiative.id).runs

    assert [(r.round, r.position) for r in runs] == [(1, 0), (1, 1), (2, 2)]
    assert runs[2].id == third.id
