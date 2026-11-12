"""The Gateway's real adapters (AD-11) and their factory.

`build_gateway` is the single decision point: it returns `LiteLLMSpend` when
`settings.gateway_enabled` is `True` and `DisabledGateway` when `False`.  No other
module in `application/` or `domain/` branches on `gateway_enabled` (AD-2).

Same pattern as `build_tracer` in `infrastructure/tracing/__init__.py`.
"""

from __future__ import annotations

import httpx

from orchestrator.domain.ports.gateway import Gateway, GatewayModels
from orchestrator.infrastructure.gateway.disabled import DisabledGateway
from orchestrator.infrastructure.gateway.litellm_models import LiteLLMModels
from orchestrator.infrastructure.gateway.litellm_spend import LiteLLMSpend
from orchestrator.infrastructure.settings import Settings


def build_gateway(settings: Settings, http: httpx.Client) -> Gateway:
    """Return `LiteLLMSpend(settings, http)` when the gateway is enabled, else `DisabledGateway()`.

    `http` is always passed by the caller (startup.py constructs it unconditionally); when
    the gateway is disabled, `DisabledGateway` never calls it — so constructing the client
    is harmless and the call shape stays minimal.
    """
    if settings.gateway_enabled:
        return LiteLLMSpend(settings, http)
    return DisabledGateway()


def build_gateway_models(settings: Settings) -> GatewayModels | None:
    """`None` when no gateway is configured, else the model list read with the API key only."""
    if not settings.gateway_enabled:
        return None
    return LiteLLMModels(settings.litellm_base_url, settings.litellm_api_key.get_secret_value())


__all__ = [
    "DisabledGateway",
    "LiteLLMModels",
    "LiteLLMSpend",
    "build_gateway",
    "build_gateway_models",
]
