"""`LiteLLMSpend` against `httpx.MockTransport` — no network (AD-11).

Every row of the story's own I/O matrix: the sum and per-model breakdown over several rows,
an empty result, a connection error, the bearer header (`LITELLM_SPEND_KEY`, never
`LITELLM_API_KEY`), pagination, and the fixed, wide date window `/spend/logs/v2` requires.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
import pytest

from orchestrator.infrastructure.gateway.litellm_spend import LiteLLMSpend
from orchestrator.infrastructure.settings import Settings

RUN_ID = UUID("00000000-0000-0000-0000-0000000000d1")
ATTEMPT_ID = UUID("00000000-0000-0000-0000-0000000000d2")

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(base_url="http://litellm.test", transport=httpx.MockTransport(handler))


def _envelope(rows: list[dict[str, Any]], *, page: int = 1, total_pages: int = 1) -> dict[str, Any]:
    return {
        "data": rows,
        "total": len(rows),
        "page": page,
        "page_size": 100,
        "total_pages": total_pages,
        "total_is_capped": False,
    }


def _row(model: str, spend: float, prompt: int, completion: int) -> dict[str, Any]:
    return {
        "spend": spend,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "model": model,
        "session_id": str(ATTEMPT_ID),
        "end_user": str(RUN_ID),
    }


def test_three_rows_two_models_sum_and_break_down_by_model(env: dict[str, str]) -> None:
    rows = [
        _row("gpt-5", 1.0, 100, 50),
        _row("gpt-5", 0.5, 40, 20),
        _row("claude-opus-5", 2.0, 200, 90),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope(rows))

    adapter = LiteLLMSpend(Settings(), _client(handler))

    spend = adapter.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.provisional is False
    assert spend.calls == 3  # noqa: PLR2004
    assert spend.usd == Decimal("3.5")
    assert spend.tokens_in == 340  # noqa: PLR2004
    assert spend.tokens_out == 160  # noqa: PLR2004
    by_model = {m.model: m for m in spend.by_model}
    assert set(by_model) == {"gpt-5", "claude-opus-5"}
    assert by_model["gpt-5"].usd == Decimal("1.5")
    assert by_model["gpt-5"].tokens_in == 140  # noqa: PLR2004
    assert by_model["claude-opus-5"].usd == Decimal("2.0")


def test_a_session_id_that_only_contains_the_attempt_id_is_excluded(env: dict[str, str]) -> None:
    """`session_id` on `/spend/logs/v2` is `LIKE %value%`, not equality (the module
    docstring, verified live) — a row whose `session_id` merely contains `ATTEMPT_ID` as a
    substring, rather than equalling it, must never be summed into a real attempt's spend."""
    real_row = _row("gpt-5", 1.0, 100, 50)
    substring_row = {
        "spend": 99.0,
        "prompt_tokens": 9,
        "completion_tokens": 9,
        "model": "gpt-5",
        "session_id": f"{ATTEMPT_ID}-not-the-same-attempt",
        "end_user": str(RUN_ID),
    }
    rows = [real_row, substring_row]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope(rows))

    adapter = LiteLLMSpend(Settings(), _client(handler))

    spend = adapter.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.provisional is False
    assert spend.calls == 1
    assert spend.usd == Decimal("1.0")


def test_an_end_user_mismatch_is_also_excluded(env: dict[str, str]) -> None:
    other_run_id = UUID("00000000-0000-0000-0000-0000000000d9")
    mismatched_row = {
        "spend": 5.0,
        "prompt_tokens": 5,
        "completion_tokens": 5,
        "model": "gpt-5",
        "session_id": str(ATTEMPT_ID),
        "end_user": str(other_run_id),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope([mismatched_row]))

    adapter = LiteLLMSpend(Settings(), _client(handler))

    spend = adapter.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.provisional is True
    assert spend.usd == Decimal("0")


def test_a_local_model_with_zero_spend_is_settled_not_empty(env: dict[str, str]) -> None:
    """Local models cost 0 with tokens (the brief's own scenario): a real row with
    `spend: 0.0` but non-zero tokens is a settled answer, not "no rows"."""
    rows = [_row("local-llama", 0.0, 128, 64)]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope(rows))

    adapter = LiteLLMSpend(Settings(), _client(handler))

    spend = adapter.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.provisional is False
    assert spend.usd == Decimal("0")
    assert spend.tokens_in == 128  # noqa: PLR2004
    assert spend.tokens_out == 64  # noqa: PLR2004
    assert spend.by_model[0].model == "local-llama"


def test_an_empty_result_is_provisional_zero_and_logs(
    env: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope([]))

    adapter = LiteLLMSpend(Settings(), _client(handler))

    spend = adapter.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.provisional is True
    assert spend.usd == Decimal("0")
    assert spend.tokens_in == 0
    assert spend.tokens_out == 0
    assert spend.by_model == ()
    assert spend.calls == 0


def test_a_connection_error_is_provisional_zero_and_never_raises(env: dict[str, str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    adapter = LiteLLMSpend(Settings(), _client(handler))

    spend = adapter.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.provisional is True
    assert spend.usd == Decimal("0")
    assert spend.calls == 0


def test_the_bearer_is_the_spend_key_never_the_api_key(env: dict[str, str]) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_envelope([]))

    settings = Settings()
    adapter = LiteLLMSpend(settings, _client(handler))

    adapter.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert len(captured) == 1
    header = captured[0].headers["authorization"]
    assert header == f"Bearer {settings.litellm_spend_key.get_secret_value()}"
    assert header != f"Bearer {settings.litellm_api_key.get_secret_value()}"


def test_a_query_names_the_end_user_and_the_session_id_and_a_wide_fixed_window(
    env: dict[str, str],
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_envelope([]))

    adapter = LiteLLMSpend(Settings(), _client(handler))

    adapter.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    params = dict(captured[0].url.params)
    assert params["end_user"] == str(RUN_ID)
    assert params["session_id"] == str(ATTEMPT_ID)
    assert params["start_date"]
    assert params["end_date"]
    assert captured[0].url.path.endswith("/spend/logs/v2")


def test_a_second_page_is_fetched_and_summed_with_the_first(env: dict[str, str]) -> None:
    page_1 = [_row("gpt-5", 1.0, 10, 5)]
    page_2 = [_row("gpt-5", 2.0, 20, 10)]

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(dict(request.url.params)["page"])
        rows = page_1 if page == 1 else page_2
        return httpx.Response(200, json=_envelope(rows, page=page, total_pages=2))

    adapter = LiteLLMSpend(Settings(), _client(handler))

    spend = adapter.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.calls == 2  # noqa: PLR2004
    assert spend.usd == Decimal("3.0")
    assert spend.tokens_in == 30  # noqa: PLR2004
    assert spend.tokens_out == 15  # noqa: PLR2004


def test_a_bad_body_is_provisional_zero_and_never_raises(env: dict[str, str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    adapter = LiteLLMSpend(Settings(), _client(handler))

    spend = adapter.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.provisional is True
    assert spend.usd == Decimal("0")


def test_a_non_object_body_is_provisional_zero_and_never_raises(env: dict[str, str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    adapter = LiteLLMSpend(Settings(), _client(handler))

    spend = adapter.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.provisional is True
    assert spend.usd == Decimal("0")


def test_unusable_row_figures_are_treated_as_zero_rather_than_raising(env: dict[str, str]) -> None:
    rows = [
        {
            "spend": "not-a-number",
            "prompt_tokens": "also-not-a-number",
            "completion_tokens": None,
            "model": "gpt-5",
            "session_id": str(ATTEMPT_ID),
            "end_user": str(RUN_ID),
        },
        {
            "spend": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "model": "gpt-5",
            "session_id": str(ATTEMPT_ID),
            "end_user": str(RUN_ID),
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope(rows))

    adapter = LiteLLMSpend(Settings(), _client(handler))

    spend = adapter.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.provisional is False
    assert spend.usd == Decimal("0")
    assert spend.tokens_in == 0
    assert spend.tokens_out == 0
    assert spend.by_model[0].model == "gpt-5"


def test_an_http_error_status_is_provisional_zero_and_never_raises(env: dict[str, str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    adapter = LiteLLMSpend(Settings(), _client(handler))

    spend = adapter.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.provisional is True
    assert spend.usd == Decimal("0")
