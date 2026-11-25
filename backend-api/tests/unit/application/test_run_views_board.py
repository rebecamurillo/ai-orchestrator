"""The Board's initiative fields and its column rule (story 4, epic 7; AD-36), imported by
the module path the cards now live at."""

from __future__ import annotations

from uuid import UUID

from orchestrator.application.use_cases import run_views
from orchestrator.application.use_cases.run_read_ports import RunReadPorts
from orchestrator.application.use_cases.run_views_board import (
    board_current_step_label,
    board_view,
)
from orchestrator.domain.entities.template import TemplateVersion
from orchestrator.domain.ids import new_id
from tests.unit.application.initiative_read_world import NOW, ReadWorld
from tests.unit.fakes.templates import FakeTemplateVersionRepository

INTERACTIVE = "name: p/spec\ntype: interactive\n"

THREE = 3


class CountingTemplates(FakeTemplateVersionRepository):
    def __init__(self, versions: list[TemplateVersion]) -> None:
        super().__init__(versions)
        self.reads: list[tuple[str, int]] = []

    def get(self, name: str, version: int) -> TemplateVersion | None:
        self.reads.append((name, version))
        return super().get(name, version)


def wired(world: ReadWorld, templates: CountingTemplates | None = None) -> RunReadPorts:
    return RunReadPorts(
        runs=world.runs,
        steps=world.steps,
        projects=world.projects,
        repositories=world.repositories,
        attempts=world.attempts,
        initiatives=world.initiatives,
        templates=templates
        or CountingTemplates(
            [TemplateVersion(name="p/spec", version=2, yaml=INTERACTIVE, hash="h")]
        ),
        workspace=world.workspace,
    )


def board(ports: RunReadPorts):  # type: ignore[no-untyped-def]
    return board_view(ports, project_id=None, now=NOW)


def test_the_board_is_the_function_run_views_re_exports() -> None:
    assert run_views.board_view is board_view


def test_a_blocked_park_stays_in_needs_you_with_its_attention() -> None:
    world = ReadWorld()
    run = world.run(world.initiative(), status="needs_you", park_kind="blocked", park_path="x")

    view = board(wired(world))

    assert [c.id for c in view.columns.needs_you] == [run.id]
    assert view.columns.needs_you[0].attention == "blocked"
    assert view.counts.needs_you == 1


def test_a_conversation_waiting_on_her_turn_files_under_running() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.parked_spec(initiative, turns=2)

    view = board(wired(world))

    assert view.columns.needs_you == []
    assert (view.counts.needs_you, view.counts.running) == (0, 1)
    (card,) = view.columns.running
    assert card.id == run.id
    assert card.attention == "your_turn"
    assert card.template_type == "interactive"
    assert card.initiative is not None
    assert (card.initiative.id, card.initiative.slug, card.initiative.step) == (
        initiative.id,
        "snake",
        "intake",
    )
    assert (card.initiative.position, card.initiative.workflow_count) == (1, 2)


def attempt_reads(world: ReadWorld) -> list[object]:
    return [call for call in world.attempts.calls if call[0] == "list_for_row"]


def test_only_a_conversation_park_reads_attempts_and_only_its_parked_row() -> None:
    """Story 4 review (2026-11-25): the Board reads no attempt a card's attention ignores."""
    world = ReadWorld()
    initiative = world.initiative()
    running = world.run(initiative, position=1, status="running")
    world.row(running, 1, status="running")
    world.run(initiative, position=2, status="needs_you", park_kind="blocked", park_path="x")
    parked = world.parked_spec(initiative, turns=2)
    (parked_row,) = [r for r in world.steps.list_for_run(parked.id) if r.path == parked.park_path]
    world.attempts.calls.clear()

    board(wired(world))

    assert attempt_reads(world) == [("list_for_row", parked_row.id)]


def test_a_conversation_park_naming_no_row_reads_no_attempts() -> None:
    """Story 4 review (2026-11-25)."""
    world = ReadWorld()
    world.run(world.initiative(), status="needs_you", park_kind="conversation", park_path="gone")
    world.attempts.calls.clear()

    view = board(wired(world))

    assert attempt_reads(world) == []
    (card,) = [*view.columns.running, *view.columns.needs_you]
    assert card.attention is not None


def test_a_run_outside_any_initiative_has_no_initiative_tag() -> None:
    world = ReadWorld()
    world.run(world.initiative(), status="running", initiative_id=None, initiative_position=None)

    (card,) = board(wired(world)).columns.running

    assert card.initiative is None


def test_a_run_naming_a_missing_initiative_has_no_tag() -> None:
    world = ReadWorld()
    world.run(world.initiative(), status="running", initiative_id=new_id())

    (card,) = board(wired(world)).columns.running

    assert card.initiative is None


def test_without_an_attempts_port_the_tag_has_no_step_and_no_attention() -> None:
    world = ReadWorld()
    world.parked_spec(world.initiative(), turns=2)
    ports = RunReadPorts(runs=world.runs, steps=world.steps, initiatives=world.initiatives)

    view = board(ports)

    (card,) = view.columns.needs_you
    assert card.attention is None
    assert card.initiative is not None
    assert card.initiative.step is None
    assert card.template_type is None


def test_a_board_with_only_runs_wired_keeps_every_needs_you_card() -> None:
    world = ReadWorld()
    world.parked_spec(world.initiative(), turns=2)

    view = board(RunReadPorts(runs=world.runs))

    (card,) = view.columns.needs_you
    assert (card.attention, card.initiative, card.template_type) == (None, None, None)


def test_the_template_type_is_read_once_per_template_version() -> None:
    world = ReadWorld()
    templates = CountingTemplates(
        [TemplateVersion(name="p/spec", version=2, yaml=INTERACTIVE, hash="h")]
    )
    initiative = world.initiative()
    world.run(initiative, position=0)
    world.run(initiative, position=1)
    world.run(initiative, position=2)

    cards = board(wired(world, templates)).columns.running

    assert len(cards) == THREE
    assert templates.reads == [("p/spec", 2)]


def test_a_stored_version_missing_leaves_the_type_unknown() -> None:
    world = ReadWorld()
    world.run(world.initiative(), status="running")

    (card,) = board(wired(world, CountingTemplates([]))).columns.running

    assert card.template_type is None


def test_the_current_step_label_is_still_reachable_by_its_public_name() -> None:
    world = ReadWorld()
    run = world.run(world.initiative())
    world.row(run, 1, status="running", label="Talk it through")

    assert board_current_step_label(run, world.steps.list_for_run(run.id)) == "Talk it through"
    assert isinstance(run.id, UUID)
