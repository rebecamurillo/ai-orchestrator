"""`run_detail`'s initiative and template type (story 4, epic 7; AD-36): the view-level half
of the Run page header."""

from __future__ import annotations

from orchestrator.application.use_cases.run_view_types import RunViewPorts
from orchestrator.application.use_cases.run_views import run_detail
from orchestrator.domain.entities.template import TemplateVersion
from orchestrator.domain.ids import new_id
from tests.unit.application.initiative_read_world import ReadWorld
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.runs import FakeGateRecordRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository


def ports(world: ReadWorld, *, wired: bool = True) -> RunViewPorts:
    templates = FakeTemplateVersionRepository(
        [
            TemplateVersion(
                name="p/spec", version=2, yaml="name: p/spec\ntype: interactive\n", hash="h"
            )
        ]
    )
    return RunViewPorts(
        runs=world.runs,
        steps=world.steps,
        attempts=world.attempts,
        gate_records=FakeGateRecordRepository(),
        projects=world.projects,
        repositories=world.repositories,
        logs=FakeLogReader(),
        clock=world.clock,
        initiatives=world.initiatives if wired else None,
        templates=templates if wired else None,
        workspace=world.workspace if wired else None,
    )


def test_an_initiative_run_carries_its_tag_and_template_type() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.parked_spec(initiative)

    detail = run_detail(ports(world), run.id)

    assert detail.initiative is not None
    assert (detail.initiative.id, detail.initiative.step) == (initiative.id, "intake")
    assert (detail.initiative.position, detail.initiative.workflow_count) == (1, 2)
    assert detail.template_type == "interactive"


def test_without_the_ports_wired_both_fields_are_none() -> None:
    world = ReadWorld()
    run = world.parked_spec(world.initiative())

    detail = run_detail(ports(world, wired=False), run.id)

    assert (detail.initiative, detail.template_type) == (None, None)


def test_a_run_outside_an_initiative_or_naming_a_missing_one_has_no_tag() -> None:
    world = ReadWorld()
    plain = world.run(world.initiative(), initiative_id=None, initiative_position=None)
    orphan = world.run(world.initiative(slug="other"), initiative_id=new_id())

    assert run_detail(ports(world), plain.id).initiative is None
    assert run_detail(ports(world), orphan.id).initiative is None


def test_an_initiative_run_with_no_conversation_row_has_no_step() -> None:
    world = ReadWorld()
    run = world.run(world.initiative(), position=2)

    detail = run_detail(ports(world), run.id)

    assert detail.initiative is not None
    assert detail.initiative.step is None
