"""Unit tests for `checks.harness_probe_line()` (story 2-2).

`harness_probe_line()` replaces `harness_line()` in `_lines()` — it calls the live probe
rather than reading the stored `enabled` flag.  `harness_line()` and its tests are
unchanged (read-only anchors); this file covers only the new function.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from orchestrator.application.preflight import checks
from orchestrator.application.preflight.model import CHECK_HARNESS, Line, PreflightRequest
from orchestrator.application.templates.plan_model import ResolvedTree
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.harness import ProbeResult
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.runs import FakeRunRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)
URL = "https://example.test/org/my-repo.git"


def repo(**overrides: object) -> Repository:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "slug": "my-repo",
        "url": URL,
        "default_branch": "main",
        "install_command": "uv sync",
        "quality_gate_command": "make check",
        "unit_test_command": "pytest -q",
        "test_globs": ("tests/**",),
        "package_manager": "uv",
        "clone_check": CloneCheck(status="ok", at=NOW, output="", bmad_version="6.11.0"),
        "created_at": NOW,
        "updated_at": NOW,
    }
    fields.update(overrides)
    return Repository(**fields)  # type: ignore[arg-type]


#: A Template that dispatches nothing — for the "no agent step" skip case.
#: Written here rather than borrowed from a shipped Template: the rule is about what a
#: tree holds, not which file it came from.
_NO_AGENT_TEMPLATE = """
name: no-agent
version: 1
description: a Template that dispatches nothing
inputs:
  project:    { type: project,    required: true }
  repository: { type: repository, required: true }
steps:
  - id: verify
    run: "{{repository.quality_gate_command}}"
    gate: deterministic
"""


def _tree_with_no_agent_step() -> ResolvedTree:
    result = validate(_NO_AGENT_TEMPLATE, templates=fixtures.repository_of_versions())
    assert result.template is not None, result.errors
    return ResolvedTree(root=result.template)


def ctx(**overrides: object) -> checks.Context:
    """A `Context` with sensible defaults; `harness_registry` defaults to empty."""
    fields: dict[str, object] = {
        "git": FakeGit(),
        "base_dir": Path("/work/my-project/my-repo/base"),
        "max_active_runs": 2,
        "repository": None,
        "runs": FakeRunRepository(),
        "harnesses": FakeHarnessRepository(),
        "req": PreflightRequest(),
        "tree": None,
        "plan": None,
        "plan_error": None,
        "harness_registry": {},
    }
    fields.update(overrides)
    return checks.Context(**fields)  # type: ignore[arg-type]


# --- skip cases -------------------------------------------------------------------------


def test_skips_when_harness_is_none() -> None:
    """No harness named in the request → skip (same guard as `harness_line`)."""
    line = checks.harness_probe_line(ctx())

    assert line.status == "skip"
    assert line.check == CHECK_HARNESS


def test_skips_when_repository_is_none() -> None:
    """Repository unresolved → skip (pre-flight AC5: all lines skip when repo missing)."""
    line = checks.harness_probe_line(
        ctx(req=PreflightRequest(harness="claude"), tree=fixtures.tree("epic"))
    )

    assert line.status == "skip"
    assert line.text == "no repository"


def test_skips_when_tree_has_no_agent_step() -> None:
    """Tree that dispatches no agent → skip; nothing to check the harness against."""
    line = checks.harness_probe_line(
        ctx(
            req=PreflightRequest(harness="claude"),
            repository=repo(),
            tree=_tree_with_no_agent_step(),
        )
    )

    assert line == Line(CHECK_HARNESS, "skip", "no agent step", None)


# --- harness not in registry -----------------------------------------------------------


def test_fails_when_harness_not_in_registry() -> None:
    """Harness name not in `ctx.harness_registry` → fail "harness not available"."""
    line = checks.harness_probe_line(
        ctx(
            req=PreflightRequest(harness="unknown"),
            repository=repo(),
            tree=fixtures.tree("epic"),
            harness_registry={},
        )
    )

    assert line.status == "fail"
    assert line.text == "harness not available"


# --- probe ok --------------------------------------------------------------------------


def test_ok_line_when_probe_returns_ok() -> None:
    """Probe returns `ok=True` → `ok` line; text must not say 'enabled' (the old word)."""
    harness = FakeHarness(
        probe_results=[
            ProbeResult(ok=True, version="2.1.258", failing_reason=None, models=["gpt-4o"])
        ]
    )
    line = checks.harness_probe_line(
        ctx(
            req=PreflightRequest(harness="claude"),
            repository=repo(),
            tree=fixtures.tree("epic"),
            harness_registry={"claude": harness},
        )
    )

    assert line.status == "ok"
    assert "enabled" not in line.text


# --- probe fail ------------------------------------------------------------------------


def test_fail_line_when_probe_returns_not_ok() -> None:
    """Probe returns `ok=False` → `fail` line whose text carries `failing_reason`."""
    harness = FakeHarness(
        probe_results=[
            ProbeResult(
                ok=False,
                version="2.1.258",
                failing_reason="cli not at pinned version 1.2.3",
                models=[],
            )
        ]
    )
    line = checks.harness_probe_line(
        ctx(
            req=PreflightRequest(harness="claude"),
            repository=repo(),
            tree=fixtures.tree("epic"),
            harness_registry={"claude": harness},
        )
    )

    assert line.status == "fail"
    assert "cli not at pinned version 1.2.3" in line.text
