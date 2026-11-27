"""The merge Run's lane and partition (epic 8 story 3, AC1's engine call and AC2)."""

from __future__ import annotations

from orchestrator.application.use_cases.initiative_advance import advance_initiative
from tests.unit.application.initiative_transition_world import MERGE, TransitionWorld


def enqueues(world: TransitionWorld) -> list[tuple[object, ...]]:
    return [args for name, args in world.harness.engine.calls if name == "enqueue"]


def test_ac1_the_merge_run_walks_on_the_hubs_main_partition() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=True)
    _, advance = world.spec_run("pass")

    advance_initiative(world.advance_ports(), advance.id)

    [(run_id, partition, lane)] = enqueues(world)
    merge = world.runs.runs[run_id]  # type: ignore[index]
    assert (merge.template_name, merge.template_version) == MERGE
    assert (partition, lane) == (f"{world.hub.id}:main", "walk")


def test_ac2_a_second_initiatives_merge_shares_the_partition_of_a_parked_first() -> None:
    world = TransitionWorld()
    first = world.ended_run(
        1,
        status="needs_you",
        template_name=MERGE[0],
        template_version=MERGE[1],
        partition_branch="main",
        lane="walk",
        park_kind="merge_conflict",
    )
    world.another_initiative("other")
    world.spec_branch(epics=True)
    _, second = world.spec_run("pass")

    advance_initiative(world.advance_ports(), second.id)

    [(second_run, partition, lane)] = enqueues(world)
    assert second_run != first.id
    assert (partition, lane) == (f"{world.hub.id}:{first.partition_branch}", first.lane)
    assert (partition, lane) == (f"{world.hub.id}:main", "walk")
