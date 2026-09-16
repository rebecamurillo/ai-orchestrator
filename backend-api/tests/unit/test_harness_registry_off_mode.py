"""Registry and seed behavior when the Gateway is off (story 9-4).

ACs 5-7: build_harnesses key set, alias_table gateway-off branch and tracing-off local
removal, seed_disabled_harness use case, harness_line with stored failing_check, and
seed_harness_table gateway-off integration that exercises real production code end to end.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import orchestrator.infrastructure.db.seed as seed_module
from orchestrator.application.preflight.checks import Context, harness_line
from orchestrator.application.preflight.model import CHECK_HARNESS, PreflightRequest
from orchestrator.application.steps import AGENT_KIND, KIND_META
from orchestrator.application.templates.model import ParsedTemplate, Step
from orchestrator.application.templates.plan_model import ResolvedTree
from orchestrator.application.use_cases.harnesses import HarnessPorts, seed_disabled_harness
from orchestrator.domain.entities.harness import Harness
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.seed import seed_harness_table
from orchestrator.infrastructure.harness import build_harnesses
from orchestrator.infrastructure.harness.registry import alias_table
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.fakes.runs import FakeRunRepository

NOW = datetime(2026, 9, 13, tzinfo=UTC)

#: The gateway-disabled reason string — matches seed.py verbatim.
GATEWAY_DISABLED_REASON = "gateway disabled (LITELLM_BASE_URL blank)"

#: A minimal contract with all 15 names, used for alias builder smoke tests.
DUMMY_CONTRACT: dict[str, str] = {
    name: "dummy"
    for name in (
        "ORCH_RUN_ID",
        "ORCH_ATTEMPT_ID",
        "ORCH_STORY_ID",
        "ORCH_HARNESS",
        "ORCH_PROJECT",
        "ORCH_TAGS",
        "ORCH_LANGFUSE_TAGS",
        "TRACEPARENT",
        "LITELLM_BASE_URL",
        "LITELLM_API_KEY",
        "LANGFUSE_BASE_URL",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_ENVIRONMENT",
        "ORCH_LOG_CONTENT",
    )
}


# ── helpers ───────────────────────────────────────────────────────────────────


def harness_ports(harnesses: list[Harness]) -> tuple[HarnessPorts, FakeUnitOfWork]:
    uow = FakeUnitOfWork()
    ports = HarnessPorts(uow=uow, harnesses=FakeHarnessRepository(harnesses))
    return ports, uow


def a_repo() -> Repository:
    return Repository(
        id=new_id(),
        project_id=new_id(),
        slug="my-repo",
        url="https://github.com/org/repo.git",
        default_branch="main",
        install_command="make install",
        quality_gate_command="make check",
        unit_test_command="make test",
        test_globs=("tests/**",),
        package_manager="uv",
        clone_check=CloneCheck(status="ok", at=NOW, output="", bmad_version="6.11.0"),
        created_at=NOW,
        updated_at=NOW,
    )


def an_agent_tree() -> ResolvedTree:
    """A minimal resolved tree that passes _has_agent_step."""
    step = Step(line=1, id="build", uses=AGENT_KIND, meta=KIND_META[AGENT_KIND])
    template = ParsedTemplate(line=1, name="story", version=1, steps=(step,))
    return ResolvedTree(root=template)


def ctx(**overrides: object) -> Context:
    fields: dict[str, object] = {
        "git": FakeGit(),
        "base_dir": Path("/work/repo"),
        "bmad_version": "6.11.0",
        "max_active_runs": 2,
        "repository": None,
        "runs": FakeRunRepository(),
        "harnesses": FakeHarnessRepository(),
        "req": PreflightRequest(),
        "tree": None,
        "plan": None,
        "plan_error": None,
    }
    fields.update(overrides)
    return Context(**fields)  # type: ignore[arg-type]


# ── seed_harness_table fake DB infrastructure ──────────────────────────────────

#: These classes are local to the test module; they mirror SQLAlchemyUnitOfWork's interface
#: so they can be dropped into seed_harness_table via monkeypatch.


class _FakeSession:
    pass


class _FakeEngine:
    def dispose(self) -> None:
        pass


class _FakeUow:
    """Context manager with a session attribute; accepts the session_factory ctor arg."""

    def __init__(self, factory: Any) -> None:
        self.session = _FakeSession()

    def __enter__(self) -> _FakeUow:
        return self

    def __exit__(self, *exc: Any) -> None:
        pass

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def _setup_seed_mocks(
    monkeypatch: pytest.MonkeyPatch,
    harness_repo: FakeHarnessRepository,
) -> None:
    """Replace all DB infrastructure in seed module with fakes."""
    monkeypatch.setattr(seed_module, "create_engine_from", lambda s: _FakeEngine())
    monkeypatch.setattr(seed_module, "create_session_factory", lambda e: None)
    monkeypatch.setattr(seed_module, "SQLAlchemyUnitOfWork", _FakeUow)
    monkeypatch.setattr(seed_module, "SQLAlchemyHarnessRepository", lambda s: harness_repo)
    monkeypatch.setattr(seed_module, "sync_pins", lambda p, pins: [])
    monkeypatch.setattr(seed_module, "seed_readiness_project", lambda p, **kw: None)
    monkeypatch.setattr(seed_module, "SQLAlchemyProjectRepository", lambda s: object())
    monkeypatch.setattr(seed_module, "SQLAlchemyRepositoryRepository", lambda s: object())
    monkeypatch.setattr(seed_module, "SubprocessGit", lambda t: object())
    monkeypatch.setattr(seed_module, "FernetCrypto", lambda k: object())
    monkeypatch.setattr(seed_module, "SystemClock", object)


# ── AC5: build_harnesses key set when gateway off ─────────────────────────────


def test_build_harnesses_gateway_off_excludes_local(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC5: registry keys = {claude, codex} when gateway is off."""
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    monkeypatch.setenv("LITELLM_API_KEY", "")
    settings = Settings()
    assert not settings.gateway_enabled

    harnesses = build_harnesses(settings, FakeProcessRunner())

    assert "local" not in harnesses
    assert "claude" in harnesses
    assert "codex" in harnesses


def test_build_harnesses_gateway_on_includes_local(env: dict[str, str]) -> None:
    """Gateway on: all three harnesses present."""
    settings = Settings()
    assert settings.gateway_enabled

    harnesses = build_harnesses(settings, FakeProcessRunner())

    assert "local" in harnesses
    assert "claude" in harnesses
    assert "codex" in harnesses


# ── alias_table: gateway-off branch ──────────────────────────────────────────


def test_alias_table_gateway_off_keys_are_claude_and_codex_only(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    monkeypatch.setenv("LITELLM_API_KEY", "")
    settings = Settings()

    table = alias_table(settings)

    assert "claude" in table
    assert "codex" in table
    assert "local" not in table


def test_alias_table_gateway_off_claude_builder_omits_auth_token(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gateway-off claude builder is claude_native_aliases, not claude_aliases."""
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    monkeypatch.setenv("LITELLM_API_KEY", "")
    settings = Settings()
    assert settings.tracing_enabled  # ensure tracing-on path in native_aliases

    table = alias_table(settings)
    aliases = table["claude"](DUMMY_CONTRACT)

    assert "ANTHROPIC_AUTH_TOKEN" not in aliases
    assert "ANTHROPIC_CUSTOM_HEADERS" in aliases  # tracing on → headers present


# ── alias_table: tracing-off local removal ────────────────────────────────────


def test_alias_table_tracing_off_removes_local_builder(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """When gateway on and tracing off, local has no alias builder."""
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    settings = Settings()
    assert settings.gateway_enabled
    assert not settings.tracing_enabled

    table = alias_table(settings)

    assert "local" not in table
    assert "claude" in table
    assert "codex" in table


# ── seed_disabled_harness use case ────────────────────────────────────────────


def test_seed_disabled_harness_marks_existing_row_disabled() -> None:
    existing = Harness(name="local", version_pin="1.18.26", enabled=True)
    ports, uow = harness_ports([existing])

    with uow:
        result = seed_disabled_harness(ports, "local", GATEWAY_DISABLED_REASON)

    assert result.enabled is False
    assert result.failing_check == GATEWAY_DISABLED_REASON
    assert result.version_pin == "1.18.26"
    assert uow.committed is True


def test_seed_disabled_harness_preserves_existing_version_pin() -> None:
    existing = Harness(name="local", version_pin="1.18.26", enabled=False)
    ports, uow = harness_ports([existing])

    with uow:
        result = seed_disabled_harness(ports, "local", GATEWAY_DISABLED_REASON)

    assert result.version_pin == "1.18.26"


def test_seed_disabled_harness_inserts_when_row_absent() -> None:
    ports, uow = harness_ports([])

    with uow:
        result = seed_disabled_harness(ports, "local", GATEWAY_DISABLED_REASON)

    assert result.enabled is False
    assert result.failing_check == GATEWAY_DISABLED_REASON
    assert result.version_pin == "unknown"
    assert uow.committed is True


def test_seed_disabled_harness_commits() -> None:
    ports, uow = harness_ports([Harness(name="local", version_pin="1.0.0")])

    with uow:
        seed_disabled_harness(ports, "local", GATEWAY_DISABLED_REASON)

    assert uow.committed is True


# ── harness_line returns fail with stored failing_check ───────────────────────


def test_harness_line_fail_carries_gateway_disabled_reason() -> None:
    """harness_line reads failing_check from the stored row and surfaces it."""
    disabled = Harness(
        name="local",
        version_pin="1.18.26",
        enabled=False,
        failing_check=GATEWAY_DISABLED_REASON,
    )
    harnesses = FakeHarnessRepository([disabled])
    line = harness_line(
        ctx(
            req=PreflightRequest(harness="local"),
            repository=a_repo(),
            tree=an_agent_tree(),
            harnesses=harnesses,
        )
    )

    assert line.check == CHECK_HARNESS
    assert line.status == "fail"
    assert line.text == f"disabled: {GATEWAY_DISABLED_REASON}"


# ── AC6: seed_harness_table gateway-off integration ───────────────────────────


def test_seed_harness_table_gateway_off_marks_local_disabled(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC6: calling seed_harness_table with LITELLM_BASE_URL blank writes
    local.enabled=False and the gateway-disabled reason."""
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    monkeypatch.setenv("LITELLM_API_KEY", "")
    settings = Settings()
    assert not settings.gateway_enabled

    harness_repo = FakeHarnessRepository()
    _setup_seed_mocks(monkeypatch, harness_repo)

    result = seed_harness_table(settings)

    local = next((h for h in result if h.name == "local"), None)
    assert local is not None, "local entry must be in seeded list"
    assert local.enabled is False
    assert local.failing_check == GATEWAY_DISABLED_REASON


def test_seed_harness_table_gateway_off_local_appears_exactly_once(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The replacement pattern avoids a duplicate local entry in the returned list."""
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    monkeypatch.setenv("LITELLM_API_KEY", "")
    settings = Settings()

    harness_repo = FakeHarnessRepository()
    _setup_seed_mocks(monkeypatch, harness_repo)

    result = seed_harness_table(settings)

    local_entries = [h for h in result if h.name == "local"]
    assert len(local_entries) == 1, f"expected 1 local entry, got {len(local_entries)}"


# ── AC7: seed_harness_table gateway-on does NOT write gateway-disabled reason ─


def test_seed_harness_table_gateway_on_does_not_disable_local(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC7: gateway-on seed never writes the gateway-disabled failing_check.
    This calls real production code — the seed pipeline runs against FakeHarnessRepository."""
    settings = Settings()
    assert settings.gateway_enabled

    harness_repo = FakeHarnessRepository()
    _setup_seed_mocks(monkeypatch, harness_repo)

    result = seed_harness_table(settings)

    local = next((h for h in result if h.name == "local"), None)
    assert local is not None, "local entry must be in seeded list"
    assert local.failing_check != GATEWAY_DISABLED_REASON
    assert local.failing_check is None  # seed_harnesses never writes failing_check
