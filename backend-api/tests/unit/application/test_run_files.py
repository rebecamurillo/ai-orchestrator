"""`read_run_file` (story 6-2, SPEC CAP-2, FR-19): `GET /runs/{id}/files`'s own use case —
the three refusals, in the order that keeps `path=../x` a 422 even inside a Run whose spec
folder it would also fail to match, and the one glob this endpoint resolves server-side.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.application.use_cases.run_files import RunFilesPorts, read_run_file
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Forbidden, Invalid, NotFound
from orchestrator.domain.ids import new_id
from tests.unit.fakes.runs import FakeRunRepository
from tests.unit.fakes.workspace import FakeWorkspace

SPEC_FOLDER = "specs/gates"
STORY_PATH = f"{SPEC_FOLDER}/stories/2-record-the-plan.md"
CONTENT = "---\nstatus: ready-for-dev\n---\n\n# Story\n"


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "needs_you",
        "budget_usd": Decimal("10"),
        "inputs": {"spec_folder": SPEC_FOLDER},
        "worktree_path": "/work/acme/widgets/wt/gates",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def ports_for(
    run: Run, files: dict[str, str], mtimes: dict[str, float] | None = None
) -> RunFilesPorts:
    return RunFilesPorts(
        runs=FakeRunRepository([run]),
        workspace=lambda root: FakeWorkspace(root, files=files, mtimes=mtimes),
    )


def test_a_literal_path_inside_the_spec_folder_is_read() -> None:
    run = a_run()
    ports = ports_for(run, {STORY_PATH: CONTENT})

    result = read_run_file(ports, run.id, STORY_PATH)

    assert result.path == STORY_PATH
    assert result.content == CONTENT
    assert result.size == len(CONTENT)


def test_a_glob_path_resolves_to_its_one_match() -> None:
    run = a_run()
    pattern = f"{SPEC_FOLDER}/stories/2-*.md"
    ports = ports_for(run, {STORY_PATH: CONTENT})

    result = read_run_file(ports, run.id, pattern)

    assert result.path == STORY_PATH


def test_a_glob_with_more_than_one_match_answers_the_newest() -> None:
    run = a_run()
    older = f"{SPEC_FOLDER}/stories/2-a.md"
    newer = f"{SPEC_FOLDER}/stories/2-b.md"
    pattern = f"{SPEC_FOLDER}/stories/2-*.md"
    ports = ports_for(run, {older: "old", newer: "new"}, mtimes={older: 1.0, newer: 2.0})

    result = read_run_file(ports, run.id, pattern)

    assert result.path == newer
    assert result.content == "new"


def test_a_glob_with_no_match_is_not_found() -> None:
    run = a_run()
    ports = ports_for(run, {})

    with pytest.raises(NotFound):
        read_run_file(ports, run.id, f"{SPEC_FOLDER}/stories/2-*.md")


def test_a_path_that_escapes_the_workspace_is_422_even_though_it_would_also_fail_scope() -> None:
    """`../x` never matches any `{spec_folder}` prefix either — the escape check has to run
    first, or this would answer 403 instead of the 422 the brief's own AC pins."""
    run = a_run()
    ports = ports_for(run, {})

    with pytest.raises(Invalid):
        read_run_file(ports, run.id, "../x")


def test_an_absolute_path_is_422() -> None:
    run = a_run()
    ports = ports_for(run, {})

    with pytest.raises(Invalid):
        read_run_file(ports, run.id, "/etc/passwd")


def test_a_well_formed_path_outside_the_spec_folder_is_403() -> None:
    run = a_run()
    ports = ports_for(run, {"elsewhere/file.md": "x"})

    with pytest.raises(Forbidden):
        read_run_file(ports, run.id, "elsewhere/file.md")


def test_a_run_with_no_spec_folder_admits_nothing() -> None:
    run = a_run(inputs={})
    ports = ports_for(run, {STORY_PATH: CONTENT})

    with pytest.raises(Forbidden):
        read_run_file(ports, run.id, STORY_PATH)


def test_a_literal_path_that_names_nothing_is_not_found() -> None:
    run = a_run()
    ports = ports_for(run, {})

    with pytest.raises(NotFound):
        read_run_file(ports, run.id, STORY_PATH)


def test_a_run_with_no_worktree_yet_is_422_not_a_crash() -> None:
    """A Run whose `git.worktree` row has not run yet has a `Workspace` with no root: every
    call raises `WorkspaceError`, caught here the same way an escaping path is."""
    run = a_run(worktree_path=None)
    ports = ports_for(run, {STORY_PATH: CONTENT})

    with pytest.raises(Invalid):
        read_run_file(ports, run.id, STORY_PATH)


def test_an_unknown_run_id_is_not_found() -> None:
    ports = RunFilesPorts(runs=FakeRunRepository(), workspace=FakeWorkspace)

    with pytest.raises(NotFound):
        read_run_file(ports, new_id(), STORY_PATH)


def test_the_initiative_folder_is_the_fallback_scope() -> None:
    """`Header.folder`'s own fallback (`run_views.py::_header`), read the same way here."""
    run = a_run(inputs={"initiative_folder": SPEC_FOLDER})
    ports = ports_for(run, {STORY_PATH: CONTENT})

    result = read_run_file(ports, run.id, STORY_PATH)

    assert result.content == CONTENT
