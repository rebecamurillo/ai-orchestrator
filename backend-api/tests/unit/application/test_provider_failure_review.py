"""`rules/provider_failure.py`, tightened after review (story 1-2, 2026-11-02): credentials never
reach a park reason, a retried event is not a failure, and prose that happens to contain a
status number or a warning is not a provider error."""

from __future__ import annotations

import json
from typing import Any

import pytest

from orchestrator.application.rules.provider_failure import (
    MAX_SCAN,
    PROVIDER_ERROR,
    from_log,
    from_raw,
)


def reason(message: str) -> str:
    return PROVIDER_ERROR.format(message=message)


def failure(text: str) -> dict[str, Any]:
    return {"type": "result", "is_error": True, "result": text}


# ── credentials ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
        ('request {"api_key":"zx81qv"} rejected', "zx81qv"),
        ("LITELLM_API_KEY=zx81qv set", "zx81qv"),
        ("ANTHROPIC_AUTH_TOKEN=zx81qv set", "zx81qv"),
        ("password: 'zx81qv' wrong", "zx81qv"),
        ('{"secret": "zx81qv"}', "zx81qv"),
        ("sent Bearer zx81qv upstream", "zx81qv"),
        ("Authorization: Bearer zx81qv", "zx81qv"),
    ],
)
def test_a_credential_never_reaches_the_reason_from_either_source(text: str, secret: str) -> None:
    message = f"429 rate limit: {text}"

    from_result = from_raw(failure(message))
    from_lines = from_log([f"Error: {message}"])

    for found in (from_result, from_lines):
        assert found is not None
        assert secret not in found
        assert "[redacted]" in found


def test_a_word_beside_a_credential_name_is_kept() -> None:
    found = from_raw(failure("429 rate limit; token budget low"))

    assert found == reason("429 rate limit; token budget low")


# ── events that are not failures ─────────────────────────────────────────────


def test_a_retried_event_is_not_a_failure() -> None:
    retry = {"type": "system", "subtype": "api_retry", "error": "rate_limit", "attempt": 1}

    assert from_raw(retry) is None
    assert from_log([json.dumps(retry)]) is None


def test_an_error_field_counts_only_on_an_error_event() -> None:
    assert from_raw({"error": {"message": "429 rate limit"}}) is None
    assert from_raw({"type": "system", "error": "429 rate limit"}) is None
    assert from_raw({"type": "error", "error": "429 rate limit"}) == reason("429 rate limit")


def test_the_errors_list_of_a_failed_result_is_read() -> None:
    raw = {
        "type": "result",
        "subtype": "error_during_execution",
        "is_error": True,
        "errors": ["setup ok", 3, "API Error: 429 rate limit"],
    }

    assert from_raw(raw) == reason("setup ok API Error: 429 rate limit")


def test_an_errors_list_that_names_no_text_is_nothing() -> None:
    assert from_raw({"is_error": True, "errors": [1, None]}) is None
    assert from_raw({"is_error": True, "errors": "429 rate limit"}) is None
    assert from_raw({"is_error": False, "errors": ["429 rate limit"]}) is None


# ── markers ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "line",
    [
        "Error in app.py:402",
        "npm error code 402",
        "Error: credit card test failed",
        "OTLPExporterError: Too Many Requests",
        "Error: langfuse flush hit a rate limit",
        "Error: disk write of 4029 bytes",
        "Error: cleared 429x cache entries",
    ],
)
def test_a_line_that_only_looks_like_a_provider_failure_is_not_one(line: str) -> None:
    assert from_log([line]) is None


def test_an_exporter_message_in_an_error_event_is_not_a_provider_failure() -> None:
    assert from_raw({"type": "error", "message": "OTLP exporter: Too Many Requests"}) is None


@pytest.mark.parametrize(
    "text",
    [
        "You've hit your monthly spend limit",
        "Quota exceeded for this project",
        "Budget has been exceeded",
        "You are out of credits",
        "Credits exhausted",
        "HTTP status 429",
        'body {"statusCode":429}',
        "Error 402",
    ],
)
def test_more_credit_and_rate_wordings_are_recognised(text: str) -> None:
    assert from_raw(failure(text)) == reason(text)
    assert from_log([f"Error: {text}"]) == reason(f"Error: {text}")


def test_an_openrouter_body_after_a_status_is_still_one() -> None:
    line = 'API Error: 402 {"error":{"message":"Insufficient credits","code":402}}'

    assert from_log([line]) == reason(line)


def test_json_after_a_prefix_is_read_as_an_event_not_as_text() -> None:
    prose = {"type": "assistant", "note": "error handling for the rate limit case"}
    failed = failure("API Error: 429 rate limit")

    assert from_log(["warning: " + json.dumps(prose)]) is None
    assert from_log(["stderr: " + json.dumps(failed)]) == reason("API Error: 429 rate limit")


# ── bounds ───────────────────────────────────────────────────────────────────


def test_a_marker_that_ends_at_the_scan_bound_is_found_and_one_past_it_is_not() -> None:
    marker = "rate limit"
    exact = "." * (MAX_SCAN - len(marker)) + marker
    past = "." * (MAX_SCAN + 1 - len(marker)) + marker

    assert from_raw(failure(exact)) is not None
    assert from_raw(failure(past)) is None


def test_a_marker_wholly_past_the_scan_bound_is_not_read() -> None:
    assert from_raw(failure("x " * MAX_SCAN + "rate limit")) is None


def test_the_message_is_cut_at_the_scan_bound_before_it_is_collapsed() -> None:
    text = "rate limit" + " " * (MAX_SCAN - len("rate limit")) + "tail"

    assert from_raw(failure(text)) == reason("rate limit")
