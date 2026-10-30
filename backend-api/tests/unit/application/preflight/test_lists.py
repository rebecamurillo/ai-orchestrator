"""The pre-flight checks that need a second look at a list file (FR-8, lines 4, 5, 7, 10)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from orchestrator.application.preflight import lists
from orchestrator.application.preflight.checks import Context
from orchestrator.application.preflight.model import (
    CHECK_EPICS_YAML,
    CHECK_SPEC_MD,
    CHECK_STORIES_YAML,
    Line,
    PreflightRequest,
)
from orchestrator.application.templates.plan_model import ID_NOT_PREFIX_FREE, Plan, PlanError
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.ids import new_id
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.runs import FakeRunRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def repo() -> Repository:
    return Repository(
        id=new_id(),
        project_id=new_id(),
        slug="my-repo",
        url="https://example.test/org/my-repo.git",
        default_branch="main",
        install_command="uv sync",
        quality_gate_command="make check",
        unit_test_command="pytest -q",
        test_globs=("tests/**",),
        package_manager="uv",
        clone_check=CloneCheck(status="ok", at=NOW, output="", bmad_version="6.11.0"),
        created_at=NOW,
        updated_at=NOW,
    )


def ctx(**overrides: object) -> Context:
    fields: dict[str, object] = {
        "git": FakeGit(),
        "base_dir": Path("/work/my-project/my-repo/base"),
        "max_active_runs": 2,
        "repository": repo(),
        "runs": FakeRunRepository(),
        "harnesses": FakeHarnessRepository(),
        "req": PreflightRequest(),
        "tree": None,
        "plan": None,
        "plan_error": None,
    }
    fields.update(overrides)
    return Context(**fields)  # type: ignore[arg-type]


EPICS_TEXT = """
- id: e1
  title: The first epic
  branch: feat/e1
  spec_folder: docs/e1
- id: e2
  title: The second epic
  branch: feat/e2
  spec_folder: docs/e2
"""

STORIES_TEXT = """
- id: "1"
  title: A
  description: does a
- id: "2"
  title: B
  description: does b
"""


def plan_with(refs: dict[str, str]) -> Plan:
    return Plan(plan_ref="sha", plan_refs=refs, rows=())


# --- epics.yaml (line 4) --------------------------------------------------------------------


def test_epics_yaml_line_is_none_when_not_initiative() -> None:
    assert lists.epics_yaml_line(ctx(tree=fixtures.tree("epic"))) is None


def test_epics_yaml_line_fails_with_the_plan_error() -> None:
    error = PlanError(reason=ID_NOT_PREFIX_FREE, item="e1-a")
    line = lists.epics_yaml_line(ctx(tree=fixtures.tree("initiative"), plan_error=error))

    assert line == Line(CHECK_EPICS_YAML, "fail", str(error))


def test_epics_yaml_line_is_none_when_no_epics_yaml_was_read() -> None:
    assert lists.epics_yaml_line(ctx(tree=fixtures.tree("initiative"), plan=plan_with({}))) is None


def test_epics_yaml_line_ok_lists_epics_branches_and_spec_folders() -> None:
    plan = plan_with({"docs/initiative/epics.yaml": "sha1"})
    git = FakeGit(files={("sha1", "docs/initiative/epics.yaml"): EPICS_TEXT})

    line = lists.epics_yaml_line(ctx(tree=fixtures.tree("initiative"), plan=plan, git=git))

    assert line is not None
    assert line.check == CHECK_EPICS_YAML
    assert line.status == "ok"
    assert line.text == "2 epics · branches feat/e1, feat/e2 · spec folders docs/e1, docs/e2"


def test_epics_entries_aggregates_more_than_one_path() -> None:
    plan = plan_with({"a/epics.yaml": "sha1", "b/epics.yaml": "sha2"})
    git = FakeGit(
        files={
            ("sha1", "a/epics.yaml"): EPICS_TEXT,
            ("sha2", "b/epics.yaml"): "- id: e3\n  title: X\n  branch: b\n  spec_folder: s\n",
        }
    )

    entries = lists.epics_entries(ctx(plan=plan, git=git))

    assert {str(entry["id"]) for entry in entries} == {"e1", "e2", "e3"}


# --- entries reading --------------------------------------------------------------------------


def test_entries_empty_without_a_plan() -> None:
    assert lists._entries(ctx(plan=None), "x/epics.yaml") == ()


def test_entries_empty_when_the_path_was_not_read() -> None:
    assert lists._entries(ctx(plan=plan_with({})), "x/epics.yaml") == ()


def test_entries_empty_when_the_file_is_gone() -> None:
    plan = plan_with({"x/epics.yaml": "sha1"})
    assert lists._entries(ctx(plan=plan, git=FakeGit(files={})), "x/epics.yaml") == ()


def test_entries_empty_when_the_text_is_not_a_list() -> None:
    plan = plan_with({"x/epics.yaml": "sha1"})
    git = FakeGit(files={("sha1", "x/epics.yaml"): "just: a mapping\n"})

    assert lists._entries(ctx(plan=plan, git=git), "x/epics.yaml") == ()


def test_entries_drops_a_non_mapping_item() -> None:
    plan = plan_with({"x/epics.yaml": "sha1"})
    git = FakeGit(files={("sha1", "x/epics.yaml"): "- a string\n- id: e1\n"})

    entries = lists._entries(ctx(plan=plan, git=git), "x/epics.yaml")

    assert [dict(entry) for entry in entries] == [{"id": "e1"}]


# --- stories.yaml (line 5) ---------------------------------------------------------------------


def test_stories_yaml_lines_fail_with_the_plan_error() -> None:
    error = PlanError(reason=ID_NOT_PREFIX_FREE, item="4-1-a")

    lines, ids = lists.stories_yaml_lines(ctx(tree=fixtures.tree("epic"), plan_error=error))

    assert lines == [Line(CHECK_STORIES_YAML, "fail", str(error))]
    assert ids == {}


def test_stories_yaml_lines_empty_without_a_plan_at_all() -> None:
    lines, ids = lists.stories_yaml_lines(ctx(plan=None))

    assert lines == []
    assert ids == {}


def test_stories_yaml_lines_empty_without_any_read() -> None:
    lines, ids = lists.stories_yaml_lines(ctx(plan=plan_with({})))

    assert lines == []
    assert ids == {}


def test_stories_yaml_lines_ok_and_ids_by_path() -> None:
    plan = plan_with({"docs/epic-1/stories.yaml": "sha1"})
    git = FakeGit(files={("sha1", "docs/epic-1/stories.yaml"): STORIES_TEXT})

    lines, ids = lists.stories_yaml_lines(ctx(plan=plan, git=git))

    assert lines == [Line(CHECK_STORIES_YAML, "ok", "docs/epic-1/stories.yaml · 2 stories")]
    assert ids == {"docs/epic-1/stories.yaml": ("1", "2")}


def test_stories_yaml_lines_drop_an_entry_with_no_id() -> None:
    plan = plan_with({"x/stories.yaml": "sha1"})
    text = '- id: "1"\n  title: A\n  description: a\n- title: no id\n  description: b\n'
    git = FakeGit(files={("sha1", "x/stories.yaml"): text})

    _, ids = lists.stories_yaml_lines(ctx(plan=plan, git=git))

    assert ids == {"x/stories.yaml": ("1",)}


# --- SPEC.md (line 7) ----------------------------------------------------------------------------


def test_spec_folders_empty_for_a_non_initiative_request_without_one() -> None:
    assert lists.spec_folders(ctx(tree=fixtures.tree("epic"))) == ()


def test_spec_folders_from_the_request_for_a_non_initiative_template() -> None:
    ctx_ = ctx(tree=fixtures.tree("epic"), req=PreflightRequest(inputs={"spec_folder": "docs/e1"}))

    assert lists.spec_folders(ctx_) == ("docs/e1",)


def test_spec_folders_ignores_a_non_string_spec_folder() -> None:
    ctx_ = ctx(tree=fixtures.tree("epic"), req=PreflightRequest(inputs={"spec_folder": 12}))

    assert lists.spec_folders(ctx_) == ()


def test_spec_folders_empty_for_an_initiative_with_no_epics_read() -> None:
    assert lists.spec_folders(ctx(tree=fixtures.tree("initiative"), plan=plan_with({}))) == ()


def test_spec_folders_from_every_epic_for_an_initiative() -> None:
    plan = plan_with({"docs/initiative/epics.yaml": "sha1"})
    git = FakeGit(files={("sha1", "docs/initiative/epics.yaml"): EPICS_TEXT})

    assert lists.spec_folders(ctx(tree=fixtures.tree("initiative"), plan=plan, git=git)) == (
        "docs/e1",
        "docs/e2",
    )


def test_spec_md_lines_empty_without_a_plan() -> None:
    assert lists.spec_md_lines(ctx(plan=None)) == []


def test_spec_md_lines_found() -> None:
    plan = Plan(plan_ref="sha", rows=())
    git = FakeGit(read_file=["# SPEC\n"])
    ctx_ = ctx(plan=plan, git=git, req=PreflightRequest(inputs={"spec_folder": "docs/e1"}))

    assert lists.spec_md_lines(ctx_) == [Line(CHECK_SPEC_MD, "ok", "docs/e1: found")]


def test_spec_md_lines_missing() -> None:
    plan = Plan(plan_ref="sha", rows=())
    git = FakeGit(read_file=[None])
    ctx_ = ctx(plan=plan, git=git, req=PreflightRequest(inputs={"spec_folder": "docs/e1"}))

    assert lists.spec_md_lines(ctx_) == [Line(CHECK_SPEC_MD, "fail", "docs/e1: missing")]


# --- existing story files (line 10) ---------------------------------------------------------------


def test_existing_story_files_skips_without_a_plan() -> None:
    assert lists.existing_story_files_line(ctx(plan=None), {}).status == "skip"


def test_existing_story_files_ok_none_without_any_ids() -> None:
    plan = plan_with({})
    assert lists.existing_story_files_line(ctx(plan=plan), {}).text == "none"


def test_existing_story_files_warns_a_match_with_its_status() -> None:
    plan = plan_with({"docs/e1/stories.yaml": "sha1"})
    git = FakeGit(
        listings={("sha1", "docs/e1/stories"): ["docs/e1/stories/1-a.md"]},
        files={("sha1", "docs/e1/stories/1-a.md"): "---\nstatus: done\n---\n\nbody\n"},
    )

    line = lists.existing_story_files_line(
        ctx(plan=plan, git=git), {"docs/e1/stories.yaml": ("1",)}
    )

    assert line.status == "warn"
    assert line.text == "docs/e1/stories/1-a.md · done"


def test_existing_story_files_unknown_status_when_the_frontmatter_has_none() -> None:
    plan = plan_with({"docs/e1/stories.yaml": "sha1"})
    git = FakeGit(
        listings={("sha1", "docs/e1/stories"): ["docs/e1/stories/1-a.md"]},
        files={("sha1", "docs/e1/stories/1-a.md"): "no frontmatter here\n"},
    )

    line = lists.existing_story_files_line(
        ctx(plan=plan, git=git), {"docs/e1/stories.yaml": ("1",)}
    )

    assert line.text == "docs/e1/stories/1-a.md · unknown"


def test_existing_story_files_uses_the_plan_ref_when_the_list_path_was_not_recorded() -> None:
    plan = Plan(plan_ref="fallback-sha", plan_refs={}, rows=())
    git = FakeGit(listings={("fallback-sha", "docs/e1/stories"): []})

    line = lists.existing_story_files_line(
        ctx(plan=plan, git=git), {"docs/e1/stories.yaml": ("1",)}
    )

    assert line.text == "none"


def test_story_matches_excludes_a_nested_file_and_a_different_id() -> None:
    listing = (
        "docs/e1/stories/1-a.md",
        "docs/e1/stories/1-notes/scratch.md",
        "docs/e1/stories/10-b.md",
    )

    assert lists._story_matches(listing, "docs/e1/stories", "1") == ["docs/e1/stories/1-a.md"]


def test_story_status_none_without_frontmatter() -> None:
    assert lists._story_status("no fence here\n") is None


def test_story_status_none_when_the_fence_never_closes() -> None:
    assert lists._story_status("---\nstatus: done\n") is None


def test_story_status_none_when_no_status_key_is_present() -> None:
    assert lists._story_status("---\ntitle: A\n---\n\nbody\n") is None


def test_story_status_reads_the_declared_value() -> None:
    assert lists._story_status("---\nstatus: in-progress\n---\n\nbody\n") == "in-progress"
