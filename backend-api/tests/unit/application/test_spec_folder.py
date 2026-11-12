"""`application/spec_folder.py`: the one place a spec folder's list-file and `SPEC.md` rules live.

Story 3 of epic 2 (AD-35, 2026-11-12). Every rule gets one single-defect fixture and the code
`findings.code_for` gives its reason; a clean folder gives nothing.
"""

from __future__ import annotations

import httpx
import pytest

from orchestrator.api.schemas.spec_folders import MAX_FILE_BYTES, MAX_FILES, MAX_TOTAL_BYTES
from orchestrator.application import findings
from orchestrator.application.spec_folder import (
    RULE_REASONS,
    SPEC_MD_MISSING,
    check_spec_folder,
    check_spec_md,
    list_kind,
    stories_directory,
    story_file_findings,
    story_files,
)
from orchestrator.application.templates.plan_model import (
    AMBIGUOUS_STORY_FILE,
    DUPLICATE_ENTRY_ID,
    ENTRY_MISSING_FIELDS,
    ID_NOT_PREFIX_FREE,
    LIST_FILE_NOT_A_LIST,
    LIST_FILE_NOT_FOUND,
)
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app

HTTP_UNPROCESSABLE = 422
LARGE = 5_000
EPICS = "epics.yaml"
STORIES = "e1/stories.yaml"
SPEC = "e1/SPEC.md"

EPICS_TEXT = "- {id: e1, title: One, branch: feat/e1, spec_folder: e1}\n"


def stories_text(*ids: str) -> str:
    return "".join(f'- {{id: "{i}", title: T{i}, description: d}}\n' for i in ids)


def clean() -> dict[str, str]:
    return {
        EPICS: EPICS_TEXT,
        STORIES: stories_text("1", "2"),
        SPEC: "# spec\n",
        "e1/stories/1-first.md": "x",
        "e1/stories/2-second.md": "x",
    }


def codes(errors: list) -> list[str | None]:  # type: ignore[type-arg]
    return [findings.code_for(e.reason) for e in errors]


def test_a_clean_folder_has_no_finding() -> None:
    assert check_spec_folder(clean()) == []
    assert check_spec_md(clean()) == []


def test_the_rule_reasons_are_the_six_list_file_reasons() -> None:
    assert RULE_REASONS == {
        LIST_FILE_NOT_FOUND,
        LIST_FILE_NOT_A_LIST,
        ENTRY_MISSING_FIELDS,
        DUPLICATE_ENTRY_ID,
        ID_NOT_PREFIX_FREE,
        AMBIGUOUS_STORY_FILE,
    }


def test_a_stories_list_an_epic_names_but_the_body_lacks_is_not_found() -> None:
    files = {EPICS: EPICS_TEXT}
    (error,) = check_spec_folder(files)
    assert error.reason == LIST_FILE_NOT_FOUND
    assert error.item == error.file == STORIES
    assert codes([error]) == ["spec-list-file-not-found"]


def test_an_epics_entry_under_a_subfolder_names_the_list_beside_it() -> None:
    files = {"docs/epics.yaml": EPICS_TEXT}
    (error,) = check_spec_folder(files)
    assert error.file == "docs/e1/stories.yaml"


def test_a_list_that_is_not_a_list() -> None:
    files = clean() | {STORIES: "id: 1\n"}
    (error,) = check_spec_folder(files)
    assert error.reason == LIST_FILE_NOT_A_LIST
    assert (error.file, error.item) == (STORIES, STORIES)


def test_a_story_entry_missing_a_field_is_named_with_its_line() -> None:
    files = clean() | {STORIES: '- {id: "1", title: T}\n'}
    (error,) = check_spec_folder(files)
    assert error.reason == ENTRY_MISSING_FIELDS
    assert (error.file, error.item, error.line) == (STORIES, "1", 1)


def test_an_entry_missing_its_id_is_named_by_position() -> None:
    files = clean() | {STORIES: stories_text("1") + "- {title: B, description: d}\n"}
    (error,) = check_spec_folder(files)
    assert error.item == "entry 1"


def test_an_epics_entry_missing_a_field() -> None:
    files = {EPICS: "- {id: e1, title: One, branch: feat/e1}\n"}
    (error,) = check_spec_folder(files)
    assert (error.reason, error.file, error.item) == (ENTRY_MISSING_FIELDS, EPICS, "e1")


def test_duplicate_ids_name_the_second_occurrence() -> None:
    files = clean() | {STORIES: stories_text("3", "3")}
    (error,) = check_spec_folder(files)
    assert error.reason == DUPLICATE_ENTRY_ID
    assert (error.file, error.item) == (STORIES, "3")
    assert codes([error]) == ["spec-duplicate-entry-id"]


def test_ids_that_are_not_prefix_free_name_the_longer() -> None:
    files = clean() | {STORIES: stories_text("4-1", "4-1-a")}
    (error,) = check_spec_folder(files)
    assert (error.reason, error.item) == (ID_NOT_PREFIX_FREE, "4-1-a")


def test_prefix_findings_follow_the_nested_scan_once_per_longer() -> None:
    # the first is what the plan raises: first shorter in list order, then first longer
    ids = ("9-x", "4-1-a-b", "4", "4-1", "4-1-a", "9")
    files = clean() | {STORIES: stories_text(*ids)}
    found = check_spec_folder(files)
    assert all(e.reason == ID_NOT_PREFIX_FREE for e in found)
    assert [e.item for e in found] == ["4-1-a-b", "4-1", "4-1-a", "9-x"]


def test_the_prefix_rule_stays_linear_on_a_large_list() -> None:
    ids = [f"{n}" for n in range(LARGE)] + [f"{n}-a" for n in range(LARGE)]
    files = clean() | {STORIES: stories_text(*ids)}
    found = [e for e in check_spec_folder(files) if e.reason == ID_NOT_PREFIX_FREE]
    assert len(found) == LARGE
    assert found[0].item == "0-a"


def test_ids_sharing_only_text_are_fine() -> None:
    files = clean() | {STORIES: stories_text("4-1", "4-10")}
    assert check_spec_folder(files) == []


def test_two_files_for_one_story_are_ambiguous() -> None:
    files = clean() | {"e1/stories/1-other.md": "x"}
    (error,) = check_spec_folder(files)
    assert (error.reason, error.item) == (AMBIGUOUS_STORY_FILE, "1")


def test_findings_come_epics_first_then_each_epics_stories() -> None:
    files = {
        EPICS: EPICS_TEXT + "- {id: e2, title: Two, branch: b, spec_folder: e2}\n",
        "e2/stories.yaml": stories_text("1", "1"),
        "e1/stories.yaml": stories_text("2", "2"),
    }
    assert [e.file for e in check_spec_folder(files)] == ["e1/stories.yaml", "e2/stories.yaml"]


def test_a_list_file_of_another_basename_is_not_checked_unless_expected() -> None:
    files = {"x/list.yaml": "id: 1\n"}
    assert check_spec_folder(files) == []
    (error,) = check_spec_folder(files, expected=["x/list.yaml"])
    assert error.reason == LIST_FILE_NOT_A_LIST


def test_plan_mode_infers_nothing_from_epics() -> None:
    files = {EPICS: EPICS_TEXT}
    assert check_spec_folder(files, expected=[EPICS]) == []


def test_plan_mode_names_an_expected_file_the_body_lacks() -> None:
    (error,) = check_spec_folder({}, expected=["a/b.yaml"])
    assert (error.reason, error.item) == (LIST_FILE_NOT_FOUND, "a/b.yaml")


def test_an_other_stories_yaml_is_checked_after_the_epics_ones() -> None:
    files = {"z/stories.yaml": stories_text("1", "1"), "a/stories.yaml": stories_text("2", "2")}
    assert [e.file for e in check_spec_folder(files)] == ["a/stories.yaml", "z/stories.yaml"]


def test_an_epics_list_with_a_scalar_item_is_not_a_list() -> None:
    files = {EPICS: "- {id: e1, title: One, branch: b}\n- not a mapping\n"}
    assert [e.reason for e in check_spec_folder(files)] == [LIST_FILE_NOT_A_LIST]


def test_helpers_choose_kind_and_directory_by_path() -> None:
    assert list_kind("a/stories.yaml") == "stories"
    assert list_kind("other.yaml") is None
    assert stories_directory("a/stories.yaml") == "a/stories"
    assert stories_directory("stories.yaml") == "stories"


def test_story_files_exclude_recursive_listings_and_other_ids() -> None:
    paths = ["d/4-1-a.md", "d/4-10-b.md", "d/4-1-notes/x.md", "d/4-1-c.txt"]
    assert story_files(paths, "d", "4-1") == ["d/4-1-a.md"]
    assert story_file_findings(paths, "d", "4-1") == []
    (error,) = story_file_findings(["d/1-a.md", "d/1-b.md"], "d", "1")
    assert (error.reason, error.item) == (AMBIGUOUS_STORY_FILE, "1")


def test_a_stories_yaml_without_spec_md_is_missing_it() -> None:
    files = clean()
    del files[SPEC]
    (error,) = check_spec_md(files)
    assert (error.reason, error.item, error.file) == (SPEC_MD_MISSING, "e1", SPEC)
    assert findings.REFUSAL_SPEC_MD_MISSING in findings.REGISTRY


def test_spec_md_folders_may_be_given_and_may_be_the_root() -> None:
    assert check_spec_md({"SPEC.md": "x"}, [""]) == []
    (error,) = check_spec_md({}, [""])
    assert (error.item, error.file) == ("", "SPEC.md")
    assert check_spec_md({}, []) == []


def test_spec_md_folders_derive_from_epics_then_other_stories() -> None:
    files = {EPICS: EPICS_TEXT + "- {id: e2}\n", "z/stories.yaml": "", "e1/stories.yaml": ""}
    assert [e.item for e in check_spec_md(files)] == ["e1", "z"]
    assert [e.file for e in check_spec_md({"stories.yaml": ""})] == ["SPEC.md"]


# --- the route's limits ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "files",
    [
        {f"f{i}.md": "" for i in range(501)},
        {"a.md": "x" * (1024 * 1024 + 1)},
        {f"f{i}.md": "x" * (1024 * 1024) for i in range(9)},
        {"": "x"},
        {"/x": "x"},
        {"a/../b": "x"},
        {"a\\b": "x"},
        {"./a": "x"},
    ],
    ids=["count", "file", "total", "empty", "absolute", "dotdot", "backslash", "dot-slash"],
)
async def test_an_oversized_or_unsafe_body_is_refused(
    env: dict[str, str], files: dict[str, str]
) -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    headers = {"Authorization": f"Bearer {env['ORCHESTRATOR_TOKEN']}"}
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as http:
        response = await http.post(
            "/api/v1/spec-folders/validate", json={"files": files}, headers=headers
        )
    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith("application/problem+json")


def test_the_limits_are_the_declared_ones() -> None:
    assert (MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES) == (500, 1024**2, 8 * 1024**2)
