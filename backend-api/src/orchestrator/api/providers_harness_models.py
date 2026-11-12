"""The models this instance offers per harness (7.3).

A module of its own because `api/providers.py` is at its 400-line cap
(`test_source_limits.py`); it re-exports `harness_models`, keeping the function identity
`app.dependency_overrides` keys on.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from orchestrator.api.providers_base import SETTINGS, from_state
from orchestrator.domain.ports.gateway import GatewayModels
from orchestrator.infrastructure.gateway import build_gateway_models
from orchestrator.infrastructure.harness.models import model_table
from orchestrator.infrastructure.harness.registry import build_harnesses
from orchestrator.infrastructure.process.runner import RealProcessRunner


def harness_models(request: Request) -> dict[str, tuple[str, ...]]:
    """The models this instance offers per harness (7.3) — configuration, not a port.

    Its own dependency rather than a field on `HarnessPorts`: nothing here opens a
    transaction, no use case reads it, and it is composed from `Settings` on every request
    precisely so an Operator's `.env` edit reaches the New workflow's select at the next
    restart without a migration (`infrastructure/harness/models.py`).
    """
    return model_table(from_state(request, SETTINGS))


GATEWAY_MODELS = "gateway_models"


@dataclass(frozen=True)
class ModelSources:
    """What `available_models` is given: gateway or `None`, `LOCAL_MODELS`, registry names."""

    gateway_models: GatewayModels | None
    local_models: tuple[str, ...]
    known: frozenset[str]


def model_sources(request: Request) -> ModelSources:
    """One `LiteLLMModels` per application, so its 60 s cache spans requests."""
    settings = from_state(request, SETTINGS)
    state = request.app.state
    if not hasattr(state, GATEWAY_MODELS):
        setattr(state, GATEWAY_MODELS, build_gateway_models(settings))
    return ModelSources(
        gateway_models=getattr(state, GATEWAY_MODELS),
        local_models=model_table(settings).get("local", ()),
        known=frozenset(build_harnesses(settings, RealProcessRunner())),
    )
