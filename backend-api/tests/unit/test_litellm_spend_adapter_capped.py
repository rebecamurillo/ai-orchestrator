"""`total_is_capped` reaches `AttemptSpend.capped` and is logged (story 5, owner decision T4,
2026-11-12)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
import structlog

from orchestrator.infrastructure.gateway.litellm_spend import SPEND_CAPPED, LiteLLMSpend
from orchestrator.infrastructure.settings import Settings

RUN_ID = UUID("00000000-0000-0000-0000-0000000000e1")
ATTEMPT_ID = UUID("00000000-0000-0000-0000-0000000000e2")


def _row() -> dict[str, Any]:
    return {
        "spend": 1.0,
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "model": "m",
        "session_id": str(ATTEMPT_ID),
        "end_user": str(RUN_ID),
    }


def _adapter(capped_by_page: list[bool]) -> LiteLLMSpend:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            json={
                "data": [_row()],
                "total_pages": len(capped_by_page),
                "total_is_capped": capped_by_page[page - 1],
            },
        )

    client = httpx.Client(base_url="http://litellm.test", transport=httpx.MockTransport(handler))
    return LiteLLMSpend(Settings(), client)


def test_a_capped_body_is_flagged_and_warned(env: dict[str, str]) -> None:
    with structlog.testing.capture_logs() as logs:
        spend = _adapter([True]).spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.capped is True
    assert [e["event"] for e in logs if e["log_level"] == "warning"] == [SPEND_CAPPED]


def test_an_uncapped_body_is_not_flagged_and_not_warned(env: dict[str, str]) -> None:
    with structlog.testing.capture_logs() as logs:
        spend = _adapter([False]).spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.capped is False
    assert not [e for e in logs if e["log_level"] == "warning"]


def test_one_capped_page_among_several_flags_the_answer(env: dict[str, str]) -> None:
    spend = _adapter([False, True, False]).spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.capped is True
    assert spend.calls == 3  # noqa: PLR2004
