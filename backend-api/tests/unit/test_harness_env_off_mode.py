"""Harness environment when the Gateway and/or Langfuse service is off (story 9-4).

AC1-4: the key set and the alias values each combination of gateway/tracing state produces.

`build_harness_env(settings)(...)` exercises the full pipeline:
  settings -> alias_table -> env_for -> harness environment dict
so every assertion here is about what that pipeline produces, not about any individual function.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness import build_harness_env
from orchestrator.infrastructure.harness.env import BASE_NAMES, HARNESS_ENV_CONTRACT
from orchestrator.infrastructure.settings import Settings

NOW = datetime(2026, 9, 13, tzinfo=UTC)
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def a_run() -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="story",
        template_version=1,
        status="running",
        budget_usd=Decimal("10.00"),
        created_at=NOW,
    )


def an_attempt(run: Run, harness: str) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=new_id(),
        n=1,
        status="running",
        harness=harness,
    )


def build(
    settings: Settings, run: Run, harness: str, *, log_content: bool = False
) -> dict[str, str]:
    """Call the full pipeline and return the result."""
    return build_harness_env(settings)(
        an_attempt(run, harness),
        run=run,
        project_slug="acme",
        project_env={},
        log_content=log_content,
        story_id="9-4",
        traceparent=TRACEPARENT,
    )


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def gateway_off_tracing_on(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Gateway off (LITELLM_BASE_URL blank), tracing on (LANGFUSE_BASE_URL set)."""
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    monkeypatch.setenv("LITELLM_API_KEY", "")
    settings = Settings()
    assert settings.tracing_enabled  # guard: LANGFUSE_BASE_URL must be non-blank in .env.example
    return settings


@pytest.fixture
def both_off(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Both services off."""
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    monkeypatch.setenv("LITELLM_API_KEY", "")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    return Settings()


@pytest.fixture
def gateway_on_tracing_off(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Gateway on, tracing off (LANGFUSE_BASE_URL blank)."""
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    return Settings()


@pytest.fixture
def both_on(env: dict[str, str]) -> Settings:
    """Both services on — the .env.example default."""
    return Settings()


# ── AC1: gateway off, tracing on, claude ──────────────────────────────────────


def test_gateway_off_tracing_on_claude_key_set_includes_contract_and_custom_headers(
    gateway_off_tracing_on: Settings,
) -> None:
    """Key set = contract union base names union {ANTHROPIC_CUSTOM_HEADERS}."""
    run = a_run()
    result = build(gateway_off_tracing_on, run, "claude")

    for name in HARNESS_ENV_CONTRACT:
        assert name in result, f"contract name {name!r} missing"
    for name in BASE_NAMES:
        assert name in result, f"base name {name!r} missing"
    assert "ANTHROPIC_CUSTOM_HEADERS" in result


def test_gateway_off_tracing_on_claude_no_anthropic_auth_token(
    gateway_off_tracing_on: Settings,
) -> None:
    """No blank credential: ANTHROPIC_AUTH_TOKEN must be absent when gateway is off (AD-5)."""
    run = a_run()
    result = build(gateway_off_tracing_on, run, "claude")

    assert "ANTHROPIC_AUTH_TOKEN" not in result


def test_gateway_off_tracing_on_claude_litellm_values_are_blank(
    gateway_off_tracing_on: Settings,
) -> None:
    run = a_run()
    result = build(gateway_off_tracing_on, run, "claude")

    assert result["LITELLM_BASE_URL"] == ""
    assert result["LITELLM_API_KEY"] == ""


def test_gateway_off_tracing_on_claude_has_exactly_two_langfuse_headers(
    gateway_off_tracing_on: Settings,
) -> None:
    """ANTHROPIC_CUSTOM_HEADERS holds exactly langfuse_session_id and langfuse_tags."""
    run = a_run()
    result = build(gateway_off_tracing_on, run, "claude")

    raw = result["ANTHROPIC_CUSTOM_HEADERS"]
    headers = raw.split("\n")
    assert len(headers) == 2, f"expected 2 headers, got {headers!r}"  # noqa: PLR2004 — two Langfuse headers (HEADER_SOURCES[:2])
    assert headers[0].startswith("langfuse_session_id: ")
    assert headers[1].startswith("langfuse_tags: ")


def test_gateway_off_tracing_on_claude_langfuse_session_id_is_run_id(
    gateway_off_tracing_on: Settings,
) -> None:
    """langfuse_session_id carries ORCH_RUN_ID — the Run's id."""
    run = a_run()
    result = build(gateway_off_tracing_on, run, "claude")

    headers = dict(line.split(": ", 1) for line in result["ANTHROPIC_CUSTOM_HEADERS"].split("\n"))
    assert headers["langfuse_session_id"] == str(run.id)


# ── AC2: both off, claude ──────────────────────────────────────────────────────


def test_both_off_claude_no_custom_headers(both_off: Settings) -> None:
    run = a_run()
    result = build(both_off, run, "claude")

    assert "ANTHROPIC_CUSTOM_HEADERS" not in result


def test_both_off_claude_no_anthropic_auth_token(both_off: Settings) -> None:
    run = a_run()
    result = build(both_off, run, "claude")

    assert "ANTHROPIC_AUTH_TOKEN" not in result


def test_both_off_claude_key_set_is_contract_plus_base(both_off: Settings) -> None:
    run = a_run()
    result = build(both_off, run, "claude")

    for name in HARNESS_ENV_CONTRACT:
        assert name in result, f"contract name {name!r} missing"
    for name in BASE_NAMES:
        assert name in result, f"base name {name!r} missing"


# ── AC3: both on (default) — five-headers guard ───────────────────────────────


def test_both_on_claude_has_five_header_lines(both_on: Settings) -> None:
    """Default mode: ANTHROPIC_CUSTOM_HEADERS holds exactly five lines (AD-11)."""
    run = a_run()
    result = build(both_on, run, "claude")

    assert "ANTHROPIC_CUSTOM_HEADERS" in result
    assert result["ANTHROPIC_CUSTOM_HEADERS"].count("\n") == 4  # noqa: PLR2004 — five AD-11 headers: 4 newlines


# ── AC4: gateway on, tracing off, local ───────────────────────────────────────


def test_gateway_on_tracing_off_local_has_no_langfuse_aliases(
    gateway_on_tracing_off: Settings,
) -> None:
    """With tracing off, local's alias builder is removed from alias_table."""
    run = a_run()
    result = build(gateway_on_tracing_off, run, "local")

    assert "LANGFUSE_BASEURL" not in result
    assert "LANGFUSE_USER_ID" not in result
