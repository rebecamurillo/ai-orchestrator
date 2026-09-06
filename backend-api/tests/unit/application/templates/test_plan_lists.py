"""The list files a plan is expanded from, and everything that can be wrong with one.

A `for_each` reads a file out of the Operator's own repository, so the file is data and not
a Template: it is loaded by `lines.load_sequence` — the same single YAML import site the
validator uses (AD-15) — and every refusal is a `PlanError` naming the Template, the line
of the loop that read it, and the entry at fault. An Operator whose `stories.yaml` is wrong
should be told which entry, not that planning failed.

Which list a loop read is decided by the resolved source's **basename**, because that is
also what decides the required fields, the label form and whether the already-done rule
applies. A loop over any other file is still a loop; it simply has no such rules.
"""

from __future__ import annotations

import pytest

from orchestrator.application.templates.lines import load_sequence
from orchestrator.application.templates.lists import (
    EPICS_KIND,
    REQUIRED_FIELDS,
    STORIES_KIND,
    check_entries,
    list_kind,
    read_list,
    stories_directory,
    story_done,
)
from orchestrator.application.templates.plan_model import (
    AMBIGUOUS_STORY_FILE,
    DUPLICATE_ENTRY_ID,
    ENTRY_MISSING_FIELDS,
    ID_NOT_PREFIX_FREE,
    LIST_FILE_NOT_A_LIST,
    LIST_FILE_NOT_FOUND,
    PlanError,
)
from orchestrator.application.templates.reader import PlanReader
from orchestrator.application.templates.rows import Frame
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit

REF = fixtures.BASE_SHA
OTHER = fixtures.WORK_SHA
PATH = "docs/epic-1/stories.yaml"
LINE = 27

#: How many entries the shared `stories.yaml` fixture holds.
STORY_COUNT = 3


def frame(*, ref: str = REF, branch: str | None = None) -> Frame:
    return Frame(
        prefix="",
        labels=(),
        ref=ref,
        scope={},
        template=fixtures.parsed("epic"),
        branch=branch,
    )


def reader(git: FakeGit) -> PlanReader:
    return PlanReader(git, base=fixtures.BASE, url=fixtures.REPOSITORY.url)


# --- load_sequence ----------------------------------------------------------------------------


def test_a_document_whose_root_is_a_sequence_loads() -> None:
    loaded = load_sequence("- id: 1\n- id: 2\n")

    assert loaded is not None
    assert list(loaded) == [{"id": 1}, {"id": 2}]


def test_a_document_whose_root_is_a_mapping_is_not_a_sequence() -> None:
    assert load_sequence("id: 1\n") is None


def test_text_that_is_not_yaml_at_all_is_not_a_sequence_and_does_not_raise() -> None:
    assert load_sequence("- [unclosed\n") is None


def test_an_empty_text_is_not_a_sequence() -> None:
    assert load_sequence("") is None


# --- which list ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("docs/epic-1/stories.yaml", STORIES_KIND),
        ("docs/initiative/epics.yaml", EPICS_KIND),
        ("stories.yaml", STORIES_KIND),
        ("docs/things.yaml", None),
    ],
)
def test_the_basename_decides_which_list_a_loop_read(path: str, kind: str | None) -> None:
    assert list_kind(path) == kind


def test_the_two_lists_require_the_fields_the_brief_names() -> None:
    assert REQUIRED_FIELDS[STORIES_KIND] == ("id", "title", "description")
    assert REQUIRED_FIELDS[EPICS_KIND] == ("id", "title", "branch", "spec_folder")


def test_a_loop_over_any_other_file_requires_nothing() -> None:
    assert REQUIRED_FIELDS.get(None) is None


@pytest.mark.parametrize(
    ("path", "directory"),
    [("docs/epic-1/stories.yaml", "docs/epic-1/stories"), ("stories.yaml", "stories")],
)
def test_the_story_folder_sits_beside_the_list_file_that_named_it(
    path: str, directory: str
) -> None:
    assert stories_directory(path) == directory


# --- reading one -------------------------------------------------------------------------------


def test_a_list_file_is_read_at_the_frames_ref_and_recorded_there() -> None:
    memo = reader(FakeGit(files={(REF, PATH): fixtures.EPIC_STORIES}))

    items, ref_used = read_list(memo, frame(), PATH, line=LINE)

    assert [entry["id"] for entry in items] == ["1", "2", "3"]
    assert ref_used == REF
    assert memo.plan_refs == {PATH: REF}


def test_a_list_file_absent_at_the_frames_ref_is_read_at_the_frames_branch_head() -> None:
    """The Initiative case: the epics list is on the base, an epic's stories are on its branch."""
    git = FakeGit(refs={"feat/x": OTHER}, files={(OTHER, PATH): fixtures.EPIC_STORIES})
    memo = reader(git)

    items, ref_used = read_list(memo, frame(branch="feat/x"), PATH, line=LINE)

    assert len(items) == STORY_COUNT
    assert ref_used == OTHER
    assert memo.plan_refs == {PATH: OTHER}


def test_a_list_file_nowhere_at_all_is_a_plan_error_naming_the_path() -> None:
    memo = reader(FakeGit(files={}))

    with pytest.raises(PlanError) as raised:
        read_list(memo, frame(), PATH, line=LINE)

    assert raised.value.reason == LIST_FILE_NOT_FOUND
    assert raised.value.item == PATH
    assert (raised.value.template, raised.value.version, raised.value.line) == ("epic", 1, LINE)


def test_a_list_file_absent_on_a_branch_the_remote_does_not_hold_is_still_not_found() -> None:
    git = FakeGit(refs={}, files={})
    memo = reader(git)

    with pytest.raises(PlanError) as raised:
        read_list(memo, frame(branch="feat/gone"), PATH, line=LINE)

    assert raised.value.reason == LIST_FILE_NOT_FOUND


def test_a_list_file_that_is_a_mapping_is_not_a_list() -> None:
    memo = reader(FakeGit(files={(REF, PATH): "id: 1\n"}))

    with pytest.raises(PlanError) as raised:
        read_list(memo, frame(), PATH, line=LINE)

    assert raised.value.reason == LIST_FILE_NOT_A_LIST


def test_a_list_file_of_scalars_is_not_a_list_of_entries() -> None:
    memo = reader(FakeGit(files={(REF, PATH): "- one\n- two\n"}))

    with pytest.raises(PlanError) as raised:
        read_list(memo, frame(), PATH, line=LINE)

    assert raised.value.reason == LIST_FILE_NOT_A_LIST


# --- checking the entries -----------------------------------------------------------------------


def entries(*ids: str) -> tuple[dict[str, object], ...]:
    return tuple(
        {"id": entry, "title": f"Story {entry}", "description": "does a thing"} for entry in ids
    )


def test_entries_that_state_every_required_field_pass() -> None:
    check_entries(entries("4-1", "4-2"), STORIES_KIND, frame(), line=LINE)


def test_a_loop_over_a_file_with_no_required_fields_checks_nothing() -> None:
    check_entries(({"anything": 1},), None, frame(), line=LINE)


def test_an_entry_missing_a_required_field_names_the_entry_by_its_id() -> None:
    items = ({"id": "4-1", "title": "A story"},)

    with pytest.raises(PlanError) as raised:
        check_entries(items, STORIES_KIND, frame(), line=LINE)

    assert raised.value.reason == ENTRY_MISSING_FIELDS
    assert raised.value.item == "4-1"


def test_a_required_field_that_is_there_but_says_nothing_is_missing() -> None:
    """A blank title commits `story 4-1:  (orchestrator)`; absent and empty are one case."""
    items = ({"id": "4-1", "title": "", "description": "d"},)

    with pytest.raises(PlanError) as raised:
        check_entries(items, STORIES_KIND, frame(), line=LINE)

    assert raised.value.reason == ENTRY_MISSING_FIELDS
    assert raised.value.item == "4-1"


def test_a_required_field_the_operator_left_blank_in_yaml_is_missing() -> None:
    """`title:` with nothing after it is `None`, which says as little as `""` does."""
    items = ({"id": "4-1", "title": None, "description": "d"},)

    with pytest.raises(PlanError):
        check_entries(items, STORIES_KIND, frame(), line=LINE)


def test_an_entry_missing_its_id_is_named_by_its_position() -> None:
    items = ({"id": "4-1", "title": "A", "description": "d"}, {"title": "B", "description": "d"})

    with pytest.raises(PlanError) as raised:
        check_entries(items, STORIES_KIND, frame(), line=LINE)

    assert raised.value.item == "entry 1"


def test_an_epics_entry_without_a_branch_or_a_spec_folder_is_incomplete() -> None:
    items = ({"id": "e1", "title": "An epic", "branch": "feat/x"},)

    with pytest.raises(PlanError) as raised:
        check_entries(items, EPICS_KIND, frame(), line=LINE)

    assert raised.value.reason == ENTRY_MISSING_FIELDS


def test_two_entries_with_the_same_id_are_a_duplicate() -> None:
    with pytest.raises(PlanError) as raised:
        check_entries(entries("4-1", "4-1"), STORIES_KIND, frame(), line=LINE)

    assert raised.value.reason == DUPLICATE_ENTRY_ID
    assert raised.value.item == "4-1"


def test_ids_that_are_not_prefix_free_are_refused_naming_the_longer_one() -> None:
    """`4-1-a` would be matched by `4-1`'s own story-file glob, so neither can be trusted."""
    with pytest.raises(PlanError) as raised:
        check_entries(entries("4-1", "4-1-a"), STORIES_KIND, frame(), line=LINE)

    assert raised.value.reason == ID_NOT_PREFIX_FREE
    assert raised.value.item == "4-1-a"


def test_ids_that_merely_share_a_prefix_are_fine() -> None:
    """`4-10` is not `4-1-…`, so the rule must compare on the separator, not on the text."""
    check_entries(entries("4-1", "4-10"), STORIES_KIND, frame(), line=LINE)


# --- the already-done rule --------------------------------------------------------------------


DIRECTORY = "docs/epic-1/stories"


def listing_git(files: dict[str, str]) -> FakeGit:
    return FakeGit(
        files={(REF, path): text for path, text in files.items()},
        listings={(REF, DIRECTORY): list(files)},
    )


def test_a_story_with_no_file_at_all_is_not_done() -> None:
    assert story_done(reader(listing_git({})), frame(), DIRECTORY, "3", LINE) is False


def test_a_story_whose_file_states_done_is_done() -> None:
    git = listing_git({f"{DIRECTORY}/3-a.md": fixtures.story_file("done")})

    assert story_done(reader(git), frame(), DIRECTORY, "3", LINE) is True


def test_a_markdown_file_in_a_folder_named_after_the_story_is_not_the_storys_file() -> None:
    """The listing is recursive, so `3-notes/scratch.md` opens the same way and is not it."""
    git = listing_git({f"{DIRECTORY}/3-notes/scratch.md": fixtures.story_file("done")})

    assert story_done(reader(git), frame(), DIRECTORY, "3", LINE) is False


def test_a_nested_file_does_not_make_a_story_ambiguous_either() -> None:
    git = listing_git(
        {
            f"{DIRECTORY}/3-a.md": fixtures.story_file("done"),
            f"{DIRECTORY}/3-notes/scratch.md": fixtures.story_file("done"),
        }
    )

    assert story_done(reader(git), frame(), DIRECTORY, "3", LINE) is True


def test_a_story_whose_file_states_something_else_is_not_done() -> None:
    git = listing_git({f"{DIRECTORY}/3-a.md": fixtures.story_file("in-progress")})

    assert story_done(reader(git), frame(), DIRECTORY, "3", LINE) is False


def test_another_storys_file_in_the_same_folder_is_not_this_ones() -> None:
    git = listing_git({f"{DIRECTORY}/30-a.md": fixtures.story_file("done")})

    assert story_done(reader(git), frame(), DIRECTORY, "3", LINE) is False


def test_a_file_that_is_not_a_story_file_is_ignored() -> None:
    git = listing_git({f"{DIRECTORY}/3-a.txt": fixtures.story_file("done")})

    assert story_done(reader(git), frame(), DIRECTORY, "3", LINE) is False


def test_two_files_matching_one_story_are_a_plan_error() -> None:
    git = listing_git(
        {
            f"{DIRECTORY}/3-a.md": fixtures.story_file("done"),
            f"{DIRECTORY}/3-b.md": fixtures.story_file("draft"),
        }
    )

    with pytest.raises(PlanError) as raised:
        story_done(reader(git), frame(), DIRECTORY, "3", LINE)

    assert raised.value.reason == AMBIGUOUS_STORY_FILE
    assert raised.value.item == "3"


def test_a_story_file_the_listing_names_but_the_tree_does_not_hold_is_not_done() -> None:
    git = FakeGit(files={}, listings={(REF, DIRECTORY): [f"{DIRECTORY}/3-a.md"]})

    assert story_done(reader(git), frame(), DIRECTORY, "3", LINE) is False


@pytest.mark.parametrize(
    "text",
    [
        "",
        "# A story\n",
        "---\ntitle: A story\n",
        "---\n- not a mapping\n---\n",
        "---\ntitle: A story\n---\n",
        "---\nstatus: [done]\n---\n",
    ],
    ids=[
        "empty",
        "no frontmatter",
        "unterminated",
        "not a mapping",
        "no status",
        "status not a word",
    ],
)
def test_a_story_file_that_states_no_terminal_status_is_not_done(text: str) -> None:
    git = listing_git({f"{DIRECTORY}/3-a.md": text})

    assert story_done(reader(git), frame(), DIRECTORY, "3", LINE) is False
