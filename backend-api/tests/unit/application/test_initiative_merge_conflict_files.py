"""A merge-conflict stop's `conflict_files` come from its `git.merge` attempt, not from the
session turns the stop opens on the same row, which carry no merge output (epic 8 story 4).
Release review 2026-11-26: the first session turn emptied the list."""

from __future__ import annotations

from orchestrator.application.use_cases.initiative_views import initiative_detail
from orchestrator.domain.ids import new_id
from tests.unit.application.test_initiative_detail_page import merge_conflict_world


def test_the_conflicted_paths_outlast_the_session_turns_on_the_merge_row() -> None:
    world, initiative, run = merge_conflict_world()
    row = next(r for r in world.steps.list_for_run(run.id) if r.kind == "git.merge")
    world.turn(row, 2, output_ref=None)
    world.turn(row, 3, output_ref=str(new_id()))

    steps = {s.id: s for s in initiative_detail(world.ports, initiative.id).workflows[0].steps}

    assert steps["merge"].conflict_files == ["initiatives/snake/PRD.md", "README.md"]
