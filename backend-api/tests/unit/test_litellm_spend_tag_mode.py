"""`LiteLLMSpend` in `attempt_tag` mode — 5.3's documented fallback, made selectable (7.2).

`x-litellm-session-id` is what puts the attempt id in the spend log's `session_id` column, and
`GET /spend/logs/v2?end_user=&session_id=` is what 5.3 reads it back with. Codex reaches the
Gateway over the `responses` wire API through `env_http_headers`, and whether that path keeps
the session header is exactly what story 7.2's runbook has the Operator measure. If it does
not, the attempt is still identified: `x-litellm-tags` lands in `request_tags`, and one of the
five positions is `attempt:{id}`.

`/spend/logs/v2` has no tag filter (`research/spend.md`), so this mode cannot narrow
server-side: it asks for the Run's rows by `end_user` and narrows to the attempt here. That is
strictly more work than the default, which is why it is a setting and not an automatic second
attempt — an automatic one would also hide the finding the runbook exists to record (hard
rule 7).

No network: `httpx.MockTransport`, the shape `test_litellm_spend_adapter.py` (frozen) uses.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
import pytest

from orchestrator.infrastructure.gateway.litellm_spend import (
    MATCH_ATTEMPT_TAG,
    MATCH_SESSION,
    LiteLLMSpend,
)
from orchestrator.infrastructure.harness.env import attempt_tag
from orchestrator.infrastructure.settings import Settings

RUN_ID = UUID("00000000-0000-0000-0000-0000000000f1")
ATTEMPT_ID = UUID("00000000-0000-0000-0000-0000000000f2")
OTHER_ATTEMPT_ID = UUID("00000000-0000-0000-0000-0000000000f3")

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(base_url="http://litellm.test", transport=httpx.MockTransport(handler))


def _envelope(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "data": rows,
        "total": len(rows),
        "page": 1,
        "page_size": 100,
        "total_pages": 1,
        "total_is_capped": False,
    }


PROMPT_TOKENS = 10
COMPLETION_TOKENS = 5


def _row(tags: Any, *, session_id: str = "", spend: float = 1.0) -> dict[str, Any]:
    return {
        "spend": spend,
        "prompt_tokens": PROMPT_TOKENS,
        "completion_tokens": COMPLETION_TOKENS,
        "model": "gpt-5.4",
        "end_user": str(RUN_ID),
        "session_id": session_id,
        "request_tags": tags,
    }


def _tags(attempt_id: UUID) -> list[str]:
    return [
        f"run:{RUN_ID}",
        attempt_tag(str(attempt_id)),
        "story:1",
        "harness:codex",
        "project:readiness",
    ]


@pytest.fixture
def tag_mode(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("LITELLM_SPEND_MATCH", MATCH_ATTEMPT_TAG)
    return Settings()


# ── the setting itself (AD-20) ──────────────────────────────────────────────────────────


def test_the_shipped_contract_leaves_the_verified_mode_in_place(env: dict[str, str]) -> None:
    assert Settings().litellm_spend_match == MATCH_SESSION


def test_an_environment_that_predates_the_setting_still_starts(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `orch_test_mode` precedent: an operator's own `.env` must not stop starting
    because a story added a field."""
    monkeypatch.delenv("LITELLM_SPEND_MATCH", raising=False)

    assert Settings().litellm_spend_match == MATCH_SESSION


def test_the_contract_file_carries_the_line(env_example: dict[str, str]) -> None:
    assert env_example["LITELLM_SPEND_MATCH"] == MATCH_SESSION


def test_a_mode_that_is_neither_is_refused_at_start_up(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LITELLM_SPEND_MATCH", "whatever")

    with pytest.raises(ValueError, match="litellm_spend_match"):
        Settings()


# ── the query ───────────────────────────────────────────────────────────────────────────


def test_the_tag_query_asks_by_end_user_and_names_no_session(tag_mode: Settings) -> None:
    seen: list[httpx.QueryParams] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params)
        return httpx.Response(200, json=_envelope([]))

    LiteLLMSpend(tag_mode, _client(handler)).spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert len(seen) == 1
    assert seen[0]["end_user"] == str(RUN_ID)
    assert "session_id" not in seen[0]


def test_the_default_query_is_still_5_3s_own(env: dict[str, str]) -> None:
    seen: list[httpx.QueryParams] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params)
        return httpx.Response(200, json=_envelope([]))

    LiteLLMSpend(Settings(), _client(handler)).spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert seen[0]["end_user"] == str(RUN_ID)
    assert seen[0]["session_id"] == str(ATTEMPT_ID)


def test_the_spend_key_is_still_the_bearer_in_tag_mode(tag_mode: Settings) -> None:
    """AD-5: the harness never holds this key, and this adapter is its only reader."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
        return httpx.Response(200, json=_envelope([]))

    LiteLLMSpend(tag_mode, _client(handler)).spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert seen == [f"Bearer {tag_mode.litellm_spend_key.get_secret_value()}"]


# ── the matching ────────────────────────────────────────────────────────────────────────


def test_a_row_tagged_with_this_attempt_is_summed(tag_mode: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope([_row(_tags(ATTEMPT_ID), spend=2.5)]))

    spend = LiteLLMSpend(tag_mode, _client(handler)).spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.provisional is False
    assert spend.calls == 1
    assert spend.usd == Decimal("2.5")
    assert spend.tokens_in == PROMPT_TOKENS
    assert spend.tokens_out == COMPLETION_TOKENS


def test_another_attempts_rows_of_the_same_run_are_dropped(tag_mode: Settings) -> None:
    """The query cannot narrow server-side, so every row of the Run comes back: the
    narrowing here is what keeps one attempt's money out of another's."""
    rows = [_row(_tags(ATTEMPT_ID), spend=1.0), _row(_tags(OTHER_ATTEMPT_ID), spend=9.0)]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope(rows))

    spend = LiteLLMSpend(tag_mode, _client(handler)).spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.calls == 1
    assert spend.usd == Decimal("1.0")


def test_tags_written_as_one_comma_joined_string_read_the_same(tag_mode: Settings) -> None:
    """`x-litellm-tags` is sent comma-joined; whether the proxy stores a JSON list or the
    string it received is its own business, and both are read here."""
    joined = ",".join(_tags(ATTEMPT_ID))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope([_row(joined)]))

    spend = LiteLLMSpend(tag_mode, _client(handler)).spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.calls == 1


@pytest.mark.parametrize("tags", [None, [], "", 7, {"attempt": str(ATTEMPT_ID)}])
def test_a_row_whose_tags_are_unusable_is_dropped(tag_mode: Settings, tags: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope([_row(tags)]))

    spend = LiteLLMSpend(tag_mode, _client(handler)).spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.provisional is True
    assert spend.calls == 0


def test_a_row_of_another_run_is_dropped_even_when_the_tag_matches(tag_mode: Settings) -> None:
    """`end_user` is exact on the route already; it is checked here for the same symmetry
    5.3's own `_matches` keeps."""
    row = _row(_tags(ATTEMPT_ID)) | {"end_user": "some-other-run"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope([row]))

    spend = LiteLLMSpend(tag_mode, _client(handler)).spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.calls == 0


def test_a_tag_that_merely_contains_the_attempt_id_is_not_a_match(tag_mode: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope([_row([f"attempt:{ATTEMPT_ID}-2"])]))

    spend = LiteLLMSpend(tag_mode, _client(handler)).spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.calls == 0


def test_the_session_column_is_not_consulted_in_tag_mode(tag_mode: Settings) -> None:
    """The whole point: the mode exists for a path that never filled that column."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope([_row(_tags(ATTEMPT_ID), session_id="")]))

    spend = LiteLLMSpend(tag_mode, _client(handler)).spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.calls == 1
