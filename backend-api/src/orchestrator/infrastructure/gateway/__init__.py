"""The Gateway's real adapters (AD-11) and their factory.

`build_gateway` is the single decision point: it returns `LiteLLMSpend` when
`settings.gateway_enabled` is `True` and `DisabledGateway` when `False`.  No other
module in `application/` or `domain/` branches on `gateway_enabled` (AD-2).

Same pattern as `build_tracer` in `infrastructure/tracing/__init__.py`.
"""

from __future__ import annotations

import httpx

from orchestrator.domain.ports.gateway import Gateway
from orchestrator.infrastructure.gateway.disabled import DisabledGateway
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


__all__ = ["DisabledGateway", "LiteLLMSpend", "build_gateway"]
