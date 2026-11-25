"""What the initiative views and the Board read off one Run (story 4, epic 7; AD-36)."""

from __future__ import annotations

from orchestrator.application.use_cases.initiative_facts import (
    current_conversation_row,
    ended_turns,
    initiative_tag,
    run_facts,
    session_turns,
    shown_indices,
    shown_number,
    step_word,
    template_type_of,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.template import TemplateVersion
from orchestrator.domain.ids import new_id
from tests.unit.application.initiative_read_world import WORKTREE, ReadWorld, sequence
from tests.unit.fakes.templates import FakeTemplateVersionRepository
from tests.unit.fakes.workspace import FakeWorkspace

STORY = "initiatives/snake/STORY.md"


def expect(world: ReadWorld, expected: object = STORY):  # type: ignore[no-untyped-def]
    initiative = (
        world.initiatives.list()[0] if world.initiatives.initiatives else world.initiative()
    )
    run = world.run(initiative, status="running", worktree_path=WORKTREE)
    row = world.row(
        run, 1, status="running", with_resolved={"step": "intake", "expect": {"files": [expected]}}
    )
    return run, row


def test_the_running_conversation_row_is_the_current_one() -> None:
    world = ReadWorld()
    run = world.run(world.initiative())
    world.row(run, 1, status="done")
    running = world.row(run, 2, status="running")
    world.row(run, 3, kind="agent", status="running")

    assert current_conversation_row(run, world.steps.list_for_run(run.id)) == running


def test_the_parked_conversation_row_is_current_when_nothing_runs() -> None:
    world = ReadWorld()
    run = world.parked_spec(world.initiative(), turns=0)
    rows = world.steps.list_for_run(run.id)

    assert current_conversation_row(run, rows) == rows[0]


def test_a_park_path_naming_no_row_falls_to_the_last_settled_conversation_row() -> None:
    world = ReadWorld()
    run = world.run(
        world.initiative(), status="needs_you", park_kind="conversation", park_path="gone"
    )
    world.row(run, 1, status="done")
    last = world.row(run, 2, status="skipped")
    world.row(run, 3, status="planned")

    assert current_conversation_row(run, world.steps.list_for_run(run.id)) == last


def test_a_run_with_no_conversation_row_has_no_current_one() -> None:
    world = ReadWorld()
    run = world.run(world.initiative())
    world.row(run, 1, kind="agent", status="done")

    assert current_conversation_row(run, world.steps.list_for_run(run.id)) is None


def test_the_step_word_is_the_status_of_the_rows_expected_file() -> None:
    world = ReadWorld()
    run, row = expect(world)
    world.files[STORY] = "---\nstatus: blocked\n---\nbody\n"

    assert step_word(run, row, world.workspace) == "blocked"


def test_the_step_word_is_none_whenever_a_piece_is_missing() -> None:
    world = ReadWorld()
    run, row = expect(world)
    world.files[STORY] = "no frontmatter"

    assert step_word(run, row, world.workspace) is None
    assert step_word(run, row, None) is None
    assert step_word(run, None, world.workspace) is None
    assert step_word(run.model_copy(update={"worktree_path": None}), row, world.workspace) is None
    world.files.clear()
    assert step_word(run, row, world.workspace) is None


def test_the_step_word_does_not_follow_a_link() -> None:
    """Story 4 review (2026-11-25): the expected file is agent-written."""
    world = ReadWorld()
    run, row = expect(world)
    linked = FakeWorkspace(WORKTREE, {STORY: "---\nstatus: blocked\n---\n"})
    linked.links.add(STORY)

    assert step_word(run, row, lambda _path: linked) is None


def test_a_path_the_workspace_refuses_reads_as_no_step_word() -> None:
    """Story 4 review (2026-11-25): one bad `expect.files[0]` must not fail every read."""
    for refused in ("../outside.md", "/etc/passwd"):
        world = ReadWorld()
        run, row = expect(world, refused)

        assert step_word(run, row, world.workspace) is None


def test_the_step_word_needs_a_literal_first_expected_file() -> None:
    world = ReadWorld()
    run, row = expect(world)
    world.files[STORY] = "---\nstatus: blocked\n---\n"

    for bad in ("initiatives/*/STORY.md", "", {"files": []}, {"files": [3]}, "files", None):
        expected = bad if isinstance(bad, dict) or bad is None else {"files": [bad]}
        shaped = row.model_copy(update={"with_resolved": {"expect": expected}})
        if isinstance(bad, str) and bad == "files":
            shaped = row.model_copy(update={"with_resolved": {"expect": "files"}})
        assert step_word(run, shaped, world.workspace) is None


def test_run_facts_carry_attention_step_and_word() -> None:
    world = ReadWorld()
    run = world.parked_spec(world.initiative(), turns=2)

    facts = run_facts(run, world.steps.list_for_run(run.id), [], world.workspace)

    assert (facts.attention, facts.step, facts.step_word) == ("your_turn", "intake", None)


def test_a_run_with_no_conversation_has_no_step() -> None:
    world = ReadWorld()
    run = world.run(world.initiative())

    assert run_facts(run, [], [], None).step is None


def test_session_turns_are_the_rows_session_attempts_by_n() -> None:
    world = ReadWorld()
    run = world.run(world.initiative())
    row = world.row(run, 1)
    other = world.row(run, 2)
    second = world.turn(row, 2)
    first = world.turn(row, 1)
    world.turn(other, 1)
    agent = Attempt(
        id=new_id(), run_id=run.id, step_run_id=row.id, n=3, status="done", role="agent"
    )

    turns = session_turns(row, [second, agent, first, *world.attempts.list_for_row(other.id)])

    assert turns == [first, second]
    live = world.turn(row, 4, status="running")
    assert ended_turns([*turns, live]) == turns


def test_shown_numbers_count_the_shown_workflows_up_to_a_position() -> None:
    seq = sequence()

    assert shown_indices(seq) == [0, 2]
    assert [shown_number(seq, p) for p in (None, 0, 1, 2)] == [1, 1, 1, 2]


def test_the_tag_numbers_the_shown_workflow_holding_the_run() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.run(initiative, position=2)

    tag = initiative_tag(initiative, run, "intake")

    assert (tag.id, tag.slug, tag.step, tag.position, tag.workflow_count) == (
        initiative.id,
        "snake",
        "intake",
        2,
        2,
    )


def version(yaml: str) -> TemplateVersion:
    return TemplateVersion(name="t", version=1, yaml=yaml, hash="h")


def test_the_template_type_is_read_once_per_version_and_defaults_to_auto() -> None:
    templates = FakeTemplateVersionRepository([version("name: t\ntype: interactive\n")])
    memo: dict[tuple[str, int], str | None] = {}

    assert template_type_of(templates, "t", 1, memo) == "interactive"
    assert template_type_of(templates, "t", 1, memo) == "interactive"
    assert template_type_of(templates, "missing", 1, memo) is None
    assert template_type_of(None, "t", 1, memo) is None
    assert template_type_of(None, "t", 2, {}) is None


def test_a_template_without_a_type_or_a_document_is_auto() -> None:
    templates = FakeTemplateVersionRepository([version("name: t\n")])

    assert template_type_of(templates, "t", 1, {}) == "auto"
    broken = FakeTemplateVersionRepository([version("- not a mapping")])
    assert template_type_of(broken, "t", 1, {}) == "auto"


def test_the_workspace_double_is_a_factory_of_rooted_trees() -> None:
    assert isinstance(ReadWorld().workspace(WORKTREE), FakeWorkspace)
