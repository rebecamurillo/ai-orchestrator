"""Tests for `concurrent_repo_lines` (story 5-2: shared-repository informed consent)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from orchestrator.application.preflight import checks, lists
from orchestrator.application.preflight.checks import Context
from orchestrator.application.preflight.model import (
    CHECK_CONCURRENT_REPO,
    PreflightRequest,
)
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.runs import FakeRunRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)
REPO_ID = new_id()


def repo() -> Repository:
    return Repository(
        id=REPO_ID,
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


def run_on(repository_id: object, *, branch: str | None, **overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": repository_id,
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "inputs": {},
        "budget_usd": Decimal("0"),
        "created_at": NOW,
        "partition_branch": branch,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def make_ctx(
    *,
    repository: Repository | None = None,
    runs: list[Run] | None = None,
    base_branch: str = "feat/s2",
    plan: object = None,
) -> Context:
    return Context(
        git=FakeGit(),
        base_dir=Path("/work/my-project/my-repo/base"),
        max_active_runs=2,
        repository=repository,
        runs=FakeRunRepository(runs or []),
        harnesses=FakeHarnessRepository(),
        req=PreflightRequest(base_branch=base_branch),
        tree=None,
        plan=plan,  # type: ignore[arg-type]
        plan_error=None,
    )


# --- no repository -----------------------------------------------------------------------


def test_returns_empty_when_repository_is_none() -> None:
    ctx = make_ctx(repository=None)
    assert lists.concurrent_repo_lines(ctx) == []


# --- partition_branch=None holders are skipped -------------------------------------------


def test_skips_holders_with_partition_branch_none() -> None:
    holder = run_on(REPO_ID, branch=None)
    ctx = make_ctx(repository=repo(), runs=[holder])

    assert lists.concurrent_repo_lines(ctx) == []


# --- same-branch holders are skipped (already a fail via branch_lines) -------------------


def test_skips_holders_whose_partition_branch_equals_new_runs_declared_branch() -> None:
    holder = run_on(REPO_ID, branch="feat/s2")
    ctx = make_ctx(repository=repo(), runs=[holder], base_branch="feat/s2")

    assert lists.concurrent_repo_lines(ctx) == []


# --- concurrent different-branch emits a warn --------------------------------------------


def test_emits_one_warn_line_for_concurrent_run_on_different_branch() -> None:
    holder = run_on(REPO_ID, branch="feat/s1")
    ctx = make_ctx(repository=repo(), runs=[holder], base_branch="feat/s2")

    lines = lists.concurrent_repo_lines(ctx)

    assert len(lines) == 1
    assert lines[0].check == CHECK_CONCURRENT_REPO
    assert lines[0].status == "warn"
    # run_label gives "{template} · {branch}"
    assert "epic" in lines[0].text
    assert "feat/s1" in lines[0].text


# --- text includes spec_folder when present on the holder --------------------------------


def test_concurrent_run_text_includes_spec_folder() -> None:
    holder = run_on(REPO_ID, branch="feat/s1", inputs={"spec_folder": "docs/epic-1"})
    ctx = make_ctx(repository=repo(), runs=[holder], base_branch="feat/s2")

    lines = lists.concurrent_repo_lines(ctx)

    assert len(lines) == 1
    assert "docs/epic-1" in lines[0].text


def test_concurrent_run_text_includes_initiative_folder() -> None:
    holder = run_on(REPO_ID, branch="feat/s1", inputs={"initiative_folder": "docs/init"})
    ctx = make_ctx(repository=repo(), runs=[holder], base_branch="feat/s2")

    lines = lists.concurrent_repo_lines(ctx)

    assert len(lines) == 1
    assert "docs/init" in lines[0].text


def test_concurrent_run_text_has_no_folder_suffix_when_neither_input_is_set() -> None:
    holder = run_on(REPO_ID, branch="feat/s1", inputs={})
    ctx = make_ctx(repository=repo(), runs=[holder], base_branch="feat/s2")

    lines = lists.concurrent_repo_lines(ctx)

    assert len(lines) == 1
    # text is only run_label: "{template} · {branch}"
    text = lines[0].text
    assert text == checks.run_label(holder)


# --- multiple concurrent runs emit multiple warn lines -----------------------------------


def test_multiple_concurrent_runs_emit_multiple_warn_lines() -> None:
    holder_a = run_on(REPO_ID, branch="feat/s1")
    holder_b = run_on(REPO_ID, branch="feat/s3")
    ctx = make_ctx(repository=repo(), runs=[holder_a, holder_b], base_branch="feat/s2")

    lines = lists.concurrent_repo_lines(ctx)

    assert all(line.check == CHECK_CONCURRENT_REPO for line in lines)
    assert all(line.status == "warn" for line in lines)
    texts = [line.text for line in lines]
    assert any("feat/s1" in t for t in texts)
    assert any("feat/s3" in t for t in texts)


# --- terminal runs are not emitted -------------------------------------------------------


def test_terminal_runs_are_not_emitted() -> None:
    done_run = run_on(REPO_ID, branch="feat/s1", status="done")
    ctx = make_ctx(repository=repo(), runs=[done_run], base_branch="feat/s2")

    assert lists.concurrent_repo_lines(ctx) == []
