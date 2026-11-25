"""The initiative list read (story 4, epic 7; AD-36): AC1-AC4 and AC8."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from orchestrator.application.use_cases.initiative_views import (
    initiative_detail,
    list_initiatives,
)
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from tests.unit.application.initiative_read_world import NOW, ReadWorld, a_project, sequence

TWO = 2
THREE = 3
FOUR = 4


def test_every_initiative_is_listed_newest_change_first_with_its_project() -> None:
    world = ReadWorld()
    other = a_project("Other", "other")
    world.projects.add(other)
    older = world.initiative(slug="older", name="Older")
    newer = world.initiative(slug="newer", name="Newer", project_id=other.id)
    world.run(older, minutes=1)
    world.run(newer, minutes=5)

    listed = list_initiatives(world.ports, project_id=None, filter="ongoing")

    assert [row.slug for row in listed.items] == ["newer", "older"]
    assert [row.project_name for row in listed.items] == ["Other", "Acme"]
    assert listed.items[0].updated_at > listed.items[1].updated_at


def test_a_project_narrows_the_list_and_an_unknown_one_is_not_found() -> None:
    world = ReadWorld()
    other = a_project("Other", "other")
    world.projects.add(other)
    world.initiative(slug="mine")
    world.initiative(slug="theirs", project_id=other.id)

    narrowed = list_initiatives(world.ports, project_id=other.id, filter="ongoing")

    assert [row.slug for row in narrowed.items] == ["theirs"]
    with pytest.raises(NotFound):
        list_initiatives(world.ports, project_id=new_id(), filter="ongoing")


def test_needs_you_keeps_only_the_rows_waiting_for_her() -> None:
    world = ReadWorld()
    waiting = world.initiative(slug="waiting")
    running = world.initiative(slug="running")
    world.run(waiting, status="needs_you", park_kind="blocked", park_path="x", park_reason="why")
    world.run(running, status="running")

    listed = list_initiatives(world.ports, project_id=None, filter="needs_you")

    assert [row.slug for row in listed.items] == ["waiting"]
    assert listed.items[0].status == "waiting for her"
    assert listed.items[0].attention == "blocked"
    assert listed.counts.need_you == 1
    assert listed.counts.oldest_wait_at == listed.items[0].updated_at


def test_old_done_and_cancelled_initiatives_leave_ongoing_and_return_under_all() -> None:
    world = ReadWorld()
    world.initiative(slug="cancelled-old", cancelled_at=NOW - timedelta(days=40))
    world.initiative(slug="merged-old", pr_merged_at=NOW - timedelta(days=40))
    world.initiative(slug="cancelled-new", cancelled_at=NOW - timedelta(days=10))
    world.initiative(slug="merged-new", pr_merged_at=NOW - timedelta(days=10))

    ongoing = list_initiatives(world.ports, project_id=None, filter="ongoing")
    everything = list_initiatives(world.ports, project_id=None, filter="all")

    assert {row.slug for row in ongoing.items} == {"cancelled-new", "merged-new"}
    assert len(everything.items) == FOUR
    assert everything.counts.cancelled == TWO
    assert everything.counts.ongoing == 0


def test_columns_follow_the_frozen_shown_workflows_without_repeats() -> None:
    world = ReadWorld()
    world.initiative(slug="a")
    world.initiative(slug="b", sequence=sequence(deploy=True))

    listed = list_initiatives(world.ports, project_id=None, filter="all")

    assert [(c.workflow, c.type) for c in listed.columns] == [
        ("spec", "interactive"),
        ("build", "auto"),
        ("deploy", "auto"),
    ]


def test_the_merge_run_reads_as_the_spec_workflow() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    world.run(initiative, position=1, status="running")

    row = list_initiatives(world.ports, project_id=None, filter="all").items[0]

    assert (row.workflow, row.position, row.workflow_count) == ("spec", 1, 2)
    assert [(f.workflow, f.type, f.state) for f in row.workflows] == [
        ("spec", "interactive", "ongoing"),
        ("build", "auto", None),
    ]


def test_the_feet_of_a_done_and_of_a_cancelled_initiative() -> None:
    world = ReadWorld()
    done = world.initiative(slug="done", pr_merged_at=NOW)
    cancelled = world.initiative(slug="cancelled", cancelled_at=NOW)
    world.run(done, position=2, status="done")
    world.run(cancelled, position=2, status="cancelled")

    rows = {r.slug: r for r in list_initiatives(world.ports, project_id=None, filter="all").items}

    assert [f.state for f in rows["done"].workflows] == ["completed", "completed"]
    assert [f.state for f in rows["cancelled"].workflows] == ["completed", None]


def test_a_parked_conversation_with_fourteen_turns_reads_your_turn() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    world.parked_spec(initiative, turns=14)

    row = list_initiatives(world.ports, project_id=None, filter="all").items[0]

    assert row.status == "running"
    assert row.attention == "your_turn"
    assert row.line == "your turn · conversation, 14 turns"
    assert row.progress == "step 1 of 3"
    assert row.step == "intake"


def test_an_auto_run_shows_its_counts_and_spend_and_the_repo_it_works_in() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    build = world.run(
        initiative,
        position=2,
        status="running",
        spend_usd=Decimal("1.5"),
        inputs={"harness": "claude"},
    )
    for seq, workdir in enumerate(["repos/ai-orchestrator", "repos/ai-orchestrator", ""], start=1):
        world.row(
            build,
            seq,
            kind="agent",
            status="done",
            with_resolved={"workdir": workdir} if workdir else {},
        )

    row = list_initiatives(world.ports, project_id=None, filter="all").items[0]

    assert row.repo_tag == ("repos/ai-orchestrator",)
    assert row.progress == "p/spec · $1.50"
    assert row.workflow == "build"
    assert row.line == "row 3 · claude"


def test_a_row_with_no_build_run_is_tagged_with_the_hub() -> None:
    world = ReadWorld()
    world.initiative()

    row = list_initiatives(world.ports, project_id=None, filter="all").items[0]

    assert row.repo_tag == ("hub",)
    assert (row.line, row.progress) == ("next workflow starting", "step 1 of 3")


def test_a_row_whose_hub_is_gone_has_no_tag() -> None:
    world = ReadWorld()
    world.initiative(repository_id=new_id())

    row = list_initiatives(world.ports, project_id=None, filter="all").items[0]

    assert row.repo_tag == ()


def test_a_blocked_advance_waits_for_her_and_counts_the_oldest_wait() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    world.advances.add(
        InitiativeAdvance(
            id=new_id(),
            initiative_id=initiative.id,
            round=1,
            position=1,
            from_run_id=new_id(),
            blocked_reason="no slot",
        )
    )

    listed = list_initiatives(world.ports, project_id=None, filter="all")

    assert listed.items[0].line == "needs you · no slot"
    assert (listed.counts.ongoing, listed.counts.need_you) == (1, 1)


def test_the_detail_of_an_unknown_initiative_is_not_found() -> None:
    with pytest.raises(NotFound):
        initiative_detail(ReadWorld().ports, new_id())


def test_the_detail_carries_the_initiative_facts() -> None:
    world = ReadWorld()
    initiative = world.initiative(branch_cleanup_error=None)
    run = world.parked_spec(initiative)

    detail = initiative_detail(world.ports, initiative.id)

    assert detail.park_seq == run.park_seq == THREE
    assert (detail.package, detail.sha, detail.first_message) == (
        "p",
        "abc123",
        "make a snake game",
    )
    assert detail.row.status == "running"
    assert [r.id for r in detail.runs] == [run.id]


def test_the_detail_of_an_initiative_with_no_run_has_park_seq_zero() -> None:
    world = ReadWorld()
    initiative = world.initiative()

    detail = initiative_detail(world.ports, initiative.id)

    assert detail.park_seq == 0
    assert detail.runs == []
    assert all(step.status == "planned" for w in detail.workflows for step in w.steps)
