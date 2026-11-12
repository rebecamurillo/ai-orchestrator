"""`LiteLLMModels` over a mock transport (epic 2 story 4, AC6)."""

from __future__ import annotations

import httpx
import pytest

from orchestrator.domain.ports.gateway import GatewayUnreachable
from orchestrator.infrastructure.gateway import LiteLLMModels, build_gateway_models
from orchestrator.infrastructure.gateway.litellm_models import CACHE_SECONDS
from orchestrator.infrastructure.settings import Settings

API_KEY = "api-key-1"
SPEND_KEY = "spend-key-2"
HTTP_SERVER_ERROR = 500


class Transport:
    def __init__(self, respond: httpx.Response) -> None:
        self.respond = respond
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond


def make(
    response: httpx.Response, clock: list[float] | None = None
) -> tuple[LiteLLMModels, Transport]:
    transport = Transport(response)
    now = clock if clock is not None else [0.0]
    adapter = LiteLLMModels(
        "http://gw:4000/", API_KEY, lambda: now[0], transport=httpx.MockTransport(transport)
    )
    return adapter, transport


def listing(*ids: str) -> httpx.Response:
    return httpx.Response(200, json={"data": [{"id": i} for i in ids]})


def test_the_request_and_the_sorted_answer() -> None:
    adapter, transport = make(listing("gpt-5", "claude-sonnet"))

    assert adapter.models() == ("claude-sonnet", "gpt-5")
    request = transport.requests[0]
    assert request.method == "GET"
    assert str(request.url) == "http://gw:4000/v1/models"
    assert request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert SPEND_KEY not in str(request.headers)


def test_the_cache_holds_for_59_seconds_and_not_for_60() -> None:
    clock = [100.0]
    adapter, transport = make(listing("a"), clock)
    adapter.models()
    clock[0] = 100.0 + CACHE_SECONDS - 1
    adapter.models()
    assert len(transport.requests) == 1
    clock[0] = 100.0 + CACHE_SECONDS
    adapter.models()
    assert len(transport.requests) == 2  # noqa: PLR2004


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(HTTP_SERVER_ERROR),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json=["x"]),
        httpx.Response(200, json={"data": "x"}),
        httpx.Response(200, json={"data": ["x"]}),
        httpx.Response(200, json={"data": [{"id": 1}]}),
        httpx.Response(200, json={"data": [{"name": "x"}]}),
    ],
    ids=["500", "not-json", "not-dict", "data-not-list", "item-not-object", "id-not-str", "no-id"],
)
def test_an_unusable_answer_raises_and_is_not_cached(response: httpx.Response) -> None:
    adapter, transport = make(response)
    for _ in range(2):
        with pytest.raises(GatewayUnreachable):
            adapter.models()
    assert len(transport.requests) == 2  # noqa: PLR2004


def test_a_transport_fault_raises() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    adapter = LiteLLMModels("http://gw", API_KEY, transport=httpx.MockTransport(boom))
    with pytest.raises(GatewayUnreachable):
        adapter.models()


def test_the_factory_answers_none_without_a_base_url(env: dict[str, str]) -> None:
    blank = Settings(**{**{k.lower(): v for k, v in env.items()}, "litellm_base_url": ""})
    assert build_gateway_models(blank) is None


def test_the_factory_builds_the_adapter_with_the_api_key_only(env: dict[str, str]) -> None:
    on = Settings(
        **{
            **{k.lower(): v for k, v in env.items()},
            "litellm_base_url": "http://gw:4000",
            "litellm_api_key": API_KEY,
            "litellm_spend_key": SPEND_KEY,
        }
    )
    adapter = build_gateway_models(on)
    assert isinstance(adapter, LiteLLMModels)
    assert SPEND_KEY not in repr(vars(adapter))
