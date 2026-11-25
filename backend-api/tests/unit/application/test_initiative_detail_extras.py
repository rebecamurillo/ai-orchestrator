"""The header and the lists of the initiative detail (story 6, epic 7; AC1, AC2, AC6, AC7)."""

from __future__ import annotations

from orchestrator.application.use_cases import initiative_detail_extras as extras
from orchestrator.application.use_cases.initiative_views import (
    InitiativeReadPorts,
    _files_ports,
    _load,
)
from orchestrator.domain.entities.initiative import FrozenSequence, FrozenWorkflow, Initiative
from tests.unit.application.initiative_read_world import GATE, STATUS_MAP, WORKTREE, ReadWorld

SPEC_FOLDER = "specs/snake"


def loaded(world: ReadWorld, initiative: Initiative):  # type: ignore[no-untyped-def]
    return _load(world.ports, initiative)


def test_the_current_step_is_the_conversation_step_of_the_latest_run() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.parked_spec(initiative)

    assert extras.current_step(loaded(world, initiative), run) == "intake"


def test_the_current_step_is_the_merge_entry_when_its_run_is_the_latest() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.run(initiative, position=1)

    assert extras.current_step(loaded(world, initiative), run) == "merge"


def test_the_current_step_is_none_for_no_run_an_auto_run_or_a_stray_position() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    assert extras.current_step(loaded(world, initiative), None) is None

    build = world.run(initiative, position=2)
    assert extras.current_step(loaded(world, initiative), build) is None

    stray = world.run(initiative, position=9, minutes=5)
    assert extras.current_step(loaded(world, initiative), stray) is None


def test_owners_are_the_round_steps_of_the_latest_spec_run_in_order() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    world.run(initiative, inputs={"round_steps": "old"})
    world.run(initiative, initiative_round=2, minutes=5, inputs={"round_steps": "ux, tech"})

    assert extras.owners(loaded(world, initiative)) == ["ux", "tech"]


def test_no_owners_without_round_steps_a_spec_run_or_a_spec_workflow() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    assert extras.owners(loaded(world, initiative)) == []

    world.run(initiative)
    assert extras.owners(loaded(world, initiative)) == []

    auto_only = FrozenSequence(
        package="p",
        sha="x",
        workflows=(
            FrozenWorkflow(
                workflow="build",
                template="p/build",
                version=1,
                type="auto",
                shown_as="workflow",
                steps=(),
            ),
        ),
        gate=GATE,
        status_map=STATUS_MAP,
    )
    other = world.initiative(slug="other", sequence=auto_only)
    assert extras.owners(loaded(world, other)) == []


def test_sessions_list_every_run_and_step_session_in_creation_order() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    first = world.run(initiative, minutes=0, status="done")
    second = world.run(
        initiative, initiative_round=2, minutes=10, status="needs_you", senior_session=True
    )
    first_row = world.row(first, 1, status="done")
    second_row = world.row(second, 1, status="checkpoint")
    one = world.session_start(first, first_row, 1, harness="claude", model="m1")
    two = world.session_start(second, second_row, 11, harness="claude", model="m2")
    world.session_start(second, second_row, 12, scope="run")
    gate_row = world.row(second, 2, kind="agent", with_resolved={})
    odd = world.session_start(second, gate_row, 13)
    stray = world.session_start(second, second_row, 14)
    del stray

    entries = extras.sessions(loaded(world, initiative))

    assert [(e.kind, e.id, e.workflow, e.step, e.round, e.state) for e in entries] == [
        ("run", first.id, "spec", None, 1, "done"),
        ("session", one.id, "spec", "intake", 1, "closed"),
        ("run", second.id, "spec", None, 2, "needs_you"),
        ("session", two.id, "spec", "intake", 2, "closed"),
        ("session", odd.id, "spec", "spec", 2, "closed"),
        ("session", entries[-1].id, "spec", "intake", 2, "open"),
    ]


def test_a_stray_run_has_no_workflow_name_and_sessions_need_the_records_port() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.run(initiative, position=9)
    data = loaded(world, initiative)

    (entry,) = extras.sessions(data)
    assert (entry.workflow, entry.id) == ("", run.id)

    bare = InitiativeReadPorts(**{**world.ports.__dict__, "records": None})
    assert _load(bare, initiative).records == {}


def test_the_auto_files_are_the_story_files_in_first_seen_order() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    build = world.run(
        initiative, position=2, worktree_path=WORKTREE, inputs={"spec_folder": SPEC_FOLDER}
    )
    world.files[f"{SPEC_FOLDER}/stories.yaml"] = (
        "- {id: '1', title: One}\n- {id: '2', title: Two}\n"
    )
    world.files[f"{SPEC_FOLDER}/stories/1-one.md"] = "x"

    files = extras.auto_files(_files_ports(world.ports))
    assert files is not None

    assert [(f.path, f.run_id) for f in files(build.id)] == [
        (f"{SPEC_FOLDER}/stories/1-one.md", build.id)
    ]


def test_auto_files_is_absent_without_a_history_port() -> None:
    assert extras.auto_files(None) is None


def test_the_header_refs_name_the_project_and_the_hub() -> None:
    world = ReadWorld()
    initiative = world.initiative()

    project = extras.project_ref(world.projects, initiative)
    hub = extras.hub_ref(world.hub)

    assert (project.id, project.name) == (world.project.id, world.project.name)  # type: ignore[union-attr]
    assert (hub.id, hub.slug) == (world.hub.id, world.hub.slug)  # type: ignore[union-attr]
    assert extras.hub_ref(None) is None
    del world.projects.projects[world.project.id]
    assert extras.project_ref(world.projects, initiative) is None
