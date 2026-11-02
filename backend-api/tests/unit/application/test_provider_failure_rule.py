"""`application/rules/provider_failure.py` (SPEC senior-unblock CAP-5, story 1-2, 2026-11-02):
a provider credit or rate failure is named from the attempt's result object, or from the tail
of its log when the result lacks it; ordinary text that merely mentions a limit is not one."""

from __future__ import annotations

import json
from typing import Any

import pytest

from orchestrator.application.rules.harness_failure import MAX_MESSAGE
from orchestrator.application.rules.provider_failure import (
    LOG_LINES,
    MAX_LINE,
    PROVIDER_ERROR,
    from_log,
    from_raw,
)

CREDITS = "API Error: 402 Insufficient credits. Add more at openrouter.ai/settings/credits"


def reason(message: str) -> str:
    return PROVIDER_ERROR.format(message=message)


# ── the result object ────────────────────────────────────────────────────────


def test_an_error_result_naming_a_credit_failure_is_a_provider_error() -> None:
    raw = {"type": "result", "is_error": True, "result": CREDITS}

    assert from_raw(raw) == reason(CREDITS)


@pytest.mark.parametrize(
    "text",
    [
        "API Error: 429 Rate limit exceeded: free-models-per-day",
        "Request failed with status 429",
        "Error: 402 Payment Required",
        "Your credit balance is too low to access the Anthropic API",
        "You exceeded your current quota, please check your plan and billing details",
        "Claude usage limit reached",
        "provider returned error: too many requests",
        "rate_limit_error: slow down",
        "Insufficient funds",
    ],
)
def test_the_credit_and_rate_wordings_are_recognised(text: str) -> None:
    assert from_raw({"is_error": True, "result": text}) == reason(text)


def test_a_result_text_counts_only_when_the_harness_called_it_an_error() -> None:
    """A successful result is the agent's own prose; it may say anything about limits."""
    raw = {"type": "result", "is_error": False, "result": "I handled the rate limit in retry.py"}

    assert from_raw(raw) is None
    assert from_raw({"result": CREDITS}) is None
    assert from_raw({"is_error": "true", "result": CREDITS}) is None


def test_an_error_that_is_not_about_credits_or_rates_is_not_a_provider_error() -> None:
    assert from_raw({"is_error": True, "result": "API Error: connection refused"}) is None
    assert from_raw({"is_error": True, "result": "Error at parser.py:4029"}) is None
    assert from_raw({"is_error": True, "result": 7}) is None


@pytest.mark.parametrize("raw", [None, {}, {"type": "turn.completed", "usage": {}}])
def test_a_result_with_no_error_text_is_not_one(raw: dict[str, Any] | None) -> None:
    assert from_raw(raw) is None


def test_a_codex_failure_event_carries_its_message_under_error() -> None:
    raw = {"type": "turn.failed", "error": {"message": "429 Too Many Requests"}}

    assert from_raw(raw) == reason("429 Too Many Requests")


def test_an_error_given_as_a_plain_string_is_read() -> None:
    raw = {"type": "error", "error": "402 Payment Required"}

    assert from_raw(raw) == reason("402 Payment Required")


def test_an_error_event_carries_its_message_at_the_top() -> None:
    raw = {"type": "error", "message": "Rate limit reached for gpt-5"}

    assert from_raw(raw) == reason("Rate limit reached for gpt-5")


def test_a_message_on_an_object_that_is_not_an_error_event_is_ignored() -> None:
    assert from_raw({"type": "assistant", "message": "Rate limit reached"}) is None


def test_an_opencode_api_error_carries_its_message_under_data() -> None:
    raw = {
        "type": "error",
        "error": {
            "name": "APIError",
            "data": {"message": "Insufficient credits", "statusCode": 402},
        },
    }

    assert from_raw(raw) == reason("Insufficient credits")


def test_a_status_code_beside_a_message_without_a_wording_still_counts() -> None:
    raw = {"type": "error", "error": {"data": {"message": "Forbidden", "statusCode": 402}}}

    assert from_raw(raw) == reason("HTTP 402: Forbidden")


def test_a_status_code_other_than_402_and_429_adds_nothing() -> None:
    raw = {"type": "error", "error": {"data": {"message": "Bad gateway", "statusCode": 502}}}

    assert from_raw(raw) is None


def test_an_error_object_without_a_text_message_is_skipped() -> None:
    assert from_raw({"type": "error", "error": {"message": 5}}) is None
    assert from_raw({"type": "error", "error": {"data": "x"}}) is None
    assert from_raw({"type": "error", "error": 5}) is None


# ── the message ──────────────────────────────────────────────────────────────


def test_the_message_is_collapsed_and_truncated_like_the_gateway_rule() -> None:
    text = "API Error: 402 insufficient credits\n" + "x " * 400

    found = from_raw({"is_error": True, "result": text})

    assert found is not None
    message = found.removeprefix("provider error: ")
    assert "\n" not in message
    assert len(message) == MAX_MESSAGE
    assert message.endswith("…")


@pytest.mark.parametrize(
    "secret",
    [
        "sk-or-v1-0123456789abcdef0123456789abcdef",
        "ghp_0123456789abcdefABCDEF0123456789abcd",
        "xoxb-1234567890-abcdefghij",
        "AKIA0123456789ABCDEF",
    ],
)
def test_a_secret_in_the_message_never_reaches_the_reason(secret: str) -> None:
    text = f"API Error: 402 insufficient credits for key {secret} on this account"

    found = from_raw({"is_error": True, "result": text})

    assert found is not None
    assert secret not in found
    assert "[redacted]" in found


def test_authorization_headers_and_key_assignments_are_redacted() -> None:
    text = "429 rate limit. Authorization: Bearer abc.def-ghi and api_key=hunter2 rejected"

    found = from_raw({"is_error": True, "result": text})

    assert found is not None
    assert "abc.def-ghi" not in found
    assert "hunter2" not in found


def test_a_long_opaque_token_is_redacted() -> None:
    token = "A1b2" * 12

    found = from_raw({"is_error": True, "result": f"429 rate limit for {token}"})

    assert found is not None
    assert token not in found


def test_a_secret_is_redacted_before_the_message_is_cut() -> None:
    secret = "sk-" + "a" * 60
    text = "429 rate limit " + "y" * (MAX_MESSAGE - 20) + " " + secret

    found = from_raw({"is_error": True, "result": text})

    assert found is not None
    assert "sk-" not in found


# ── the log ──────────────────────────────────────────────────────────────────


def jsonl(*objects: dict[str, Any]) -> list[str]:
    return [json.dumps(each) for each in objects]


def test_a_result_event_in_the_log_names_the_error_when_the_raw_result_did_not() -> None:
    lines = jsonl(
        {"type": "system", "subtype": "init"},
        {"type": "result", "is_error": True, "result": CREDITS},
    )

    assert from_log(lines) == reason(CREDITS)


def test_a_plain_text_error_line_in_the_log_is_read() -> None:
    lines = ["npm warn something", "Error: 402 Payment Required from provider", "exit 1"]

    assert from_log(lines) == reason("Error: 402 Payment Required from provider")


def test_the_last_matching_line_wins() -> None:
    lines = ["Error: 429 first", "Error: 402 Payment Required"]

    assert from_log(lines) == reason("Error: 402 Payment Required")


def test_a_plain_line_mentioning_a_limit_without_being_an_error_is_ignored() -> None:
    lines = ["I added a rate limit to the client", "credits section updated in README"]

    assert from_log(lines) is None


def test_an_assistant_event_that_mentions_a_limit_is_the_agents_prose_not_a_failure() -> None:
    text = "Error handling now covers the rate limit case"
    lines = jsonl({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})

    assert from_log(lines) is None


def test_a_json_line_that_is_not_an_error_event_is_never_read_as_text() -> None:
    lines = jsonl({"type": "user", "content": "Error: 429 rate limit"}, {"type": "x"})

    assert from_log(lines) is None


def test_json_lines_that_are_not_objects_fall_back_to_plain_text_reading() -> None:
    assert from_log(["[1, 2]", "null"]) is None
    assert from_log(['"Error: 402 Payment Required"']) == reason('"Error: 402 Payment Required"')


def test_a_brace_line_that_is_not_json_is_read_as_text() -> None:
    assert from_log(["{ Error: 429 too many requests"]) == reason("{ Error: 429 too many requests")


def test_blank_lines_and_an_empty_log_name_nothing() -> None:
    assert from_log([]) is None
    assert from_log(["", "   "]) is None


def test_a_line_longer_than_the_bound_is_skipped() -> None:
    giant = "Error: 429 rate limit " + "z" * MAX_LINE

    assert from_log([giant]) is None


def test_only_the_last_lines_are_examined() -> None:
    lines = ["Error: 429 rate limit"] + ["ok"] * LOG_LINES

    assert from_log(lines) is None


def test_a_secret_in_a_log_line_never_reaches_the_reason() -> None:
    secret = "sk-or-v1-0123456789abcdef0123456789abcdef"

    found = from_log([f"Error: 402 insufficient credits (key {secret})"])

    assert found is not None
    assert secret not in found
