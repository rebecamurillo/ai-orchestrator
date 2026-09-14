"""DisabledGateway adapter and build_gateway factory (story 9-3).

ACs 1-3: DisabledGateway protocol conformance and spend_for_attempt return value.
Factory ACs: build_gateway routes to the right adapter based on gateway_enabled.
Startup wiring AC: walker_deps holds a DisabledGateway when the gateway is off.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from orchestrator.domain.ports.gateway import Gateway
from orchestrator.infrastructure.dbos.startup import walker_deps
from orchestrator.infrastructure.gateway import LiteLLMSpend, build_gateway
from orchestrator.infrastructure.gateway.disabled import DisabledGateway
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.gateway import PROVISIONAL_ZERO
from tests.unit.fakes.git import FakeGit


def sessions() -> Any:
    def factory() -> Any:  # pragma: no cover — never called: nothing here opens a session
        raise AssertionError("no session is opened while the deps are built")

    return factory


def poisoned_client() -> httpx.Client:
    """An httpx.Client whose request/get methods raise — proves DisabledGateway never calls it."""
    client = MagicMock(spec=httpx.Client)
    client.request.side_effect = AssertionError("DisabledGateway must not call the http client")
    client.get.side_effect = AssertionError("DisabledGateway must not call the http client")
    return client


# --- AC 1: build_gateway returns DisabledGateway when LITELLM_BASE_URL is blank ---


def test_build_gateway_returns_disabled_gateway_when_off(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    result = build_gateway(Settings(), poisoned_client())
    assert isinstance(result, DisabledGateway)


def test_disabled_gateway_satisfies_gateway_protocol(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    result = build_gateway(Settings(), poisoned_client())
    assert isinstance(result, Gateway)


def test_build_gateway_off_does_not_call_client(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The poisoned client raises on any call — this test passes only if it is never used."""
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    build_gateway(Settings(), poisoned_client())  # must not raise


# --- AC 2: build_gateway returns LiteLLMSpend with the committed .env.example environment ---


def test_build_gateway_returns_litellm_spend_when_on(env: dict[str, str]) -> None:
    result = build_gateway(Settings(), httpx.Client())
    assert isinstance(result, LiteLLMSpend)


# --- AC 3: DisabledGateway.spend_for_attempt returns PROVISIONAL_ZERO for any ids ---


def test_disabled_gateway_spend_for_attempt_returns_provisional_zero() -> None:
    gateway = DisabledGateway()
    result = gateway.spend_for_attempt(uuid.uuid4(), uuid.uuid4())
    assert result == PROVISIONAL_ZERO


def test_disabled_gateway_spend_for_attempt_never_raises() -> None:
    """Must not raise even with arbitrary UUIDs."""
    gateway = DisabledGateway()
    gateway.spend_for_attempt(uuid.uuid4(), uuid.uuid4())


# --- Startup wiring AC: walker_deps uses DisabledGateway when LITELLM_BASE_URL="" ---


def test_walker_deps_uses_disabled_gateway_when_off(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gateway in spend_writes is DisabledGateway when the base URL is blank.

    `open_spend_ports(session_factory, gateway)` is partial-ed as positional args so
    `spend_writes.args[1]` is the gateway object (startup.py Design Notes).
    """
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    deps = walker_deps(Settings(), sessions(), FakeGit())
    assert deps.step_ports.spend_writes is not None
    assert isinstance(deps.step_ports.spend_writes.args[1], DisabledGateway)
    assert deps.on_terminal is not None
    assert isinstance(deps.on_terminal.args[3], DisabledGateway)
