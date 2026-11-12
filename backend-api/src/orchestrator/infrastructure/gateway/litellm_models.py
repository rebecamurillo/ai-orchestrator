"""`GatewayModels` over LiteLLM's `GET /v1/models`, for the instance's own API key.

Takes the key as a parameter and imports no `Settings`, so `LITELLM_SPEND_KEY` cannot reach it
(hard rule 5). A failed read is not cached and not retried (hard rule 7).
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from orchestrator.domain.ports.gateway import GatewayUnreachable

CACHE_SECONDS = 60
MODELS_PATH = "/v1/models"
TIMEOUT_SECONDS = 10.0


class LiteLLMModels:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        now: Callable[[], float] = time.monotonic,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + MODELS_PATH
        self._api_key = api_key
        self._now = now
        self._transport = transport
        self._cached: tuple[float, tuple[str, ...]] | None = None

    def models(self) -> tuple[str, ...]:
        if self._cached is not None and self._now() - self._cached[0] < CACHE_SECONDS:
            return self._cached[1]
        ids = self._read()
        self._cached = (self._now(), ids)
        return ids

    def _read(self) -> tuple[str, ...]:
        try:
            with httpx.Client(transport=self._transport, timeout=TIMEOUT_SECONDS) as client:
                response = client.get(
                    self._url, headers={"Authorization": f"Bearer {self._api_key}"}
                )
        except httpx.HTTPError as error:
            raise GatewayUnreachable(f"gateway request failed: {type(error).__name__}") from error
        if not response.is_success:
            raise GatewayUnreachable(f"gateway answered {response.status_code}")
        try:
            body = response.json()
        except ValueError as error:
            raise GatewayUnreachable("gateway answered a body that is not JSON") from error
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise GatewayUnreachable("gateway body has no `data` list")
        ids: list[str] = []
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise GatewayUnreachable("gateway `data` holds an item without a string `id`")
            ids.append(item["id"])
        return tuple(sorted(ids))
