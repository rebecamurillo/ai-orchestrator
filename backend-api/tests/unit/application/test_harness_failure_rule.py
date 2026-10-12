"""`application/rules/harness_failure.py` (O-5 of _bmad-output/specs/unattended-hub-run/PLAN.md):
an `is_error` result with no output tokens is an unreachable gateway, and nothing else is."""

from __future__ import annotations

import pytest

from orchestrator.application.rules.harness_failure import (
    CAP_SUBTYPE,
    GATEWAY_UNREACHABLE,
    MAX_MESSAGE,
    gateway_unreachable,
)

ERROR = {"is_error": True, "subtype": "error_during_execution", "result": "API Error: refused"}


def test_an_error_result_without_output_is_an_unreachable_gateway() -> None:
    assert gateway_unreachable(ERROR, 0) == GATEWAY_UNREACHABLE.format(message="API Error: refused")


def test_unknown_output_tokens_count_as_none_produced() -> None:
    assert gateway_unreachable(ERROR, None) is not None


@pytest.mark.parametrize("raw", [None, {}, {"is_error": False}, {"is_error": "yes"}])
def test_a_result_that_does_not_report_an_error_is_not_one(raw: dict[str, object] | None) -> None:
    assert gateway_unreachable(raw, 0) is None


def test_an_attempt_that_produced_output_reached_the_model() -> None:
    assert gateway_unreachable(ERROR, 12) is None


def test_the_budget_cap_stop_is_the_budget_rules_not_this_ones() -> None:
    assert gateway_unreachable({"is_error": True, "subtype": CAP_SUBTYPE}, 0) is None


def test_the_message_is_collapsed_and_truncated() -> None:
    long = {"is_error": True, "result": "API Error:\n" + "x" * 500}

    reason = gateway_unreachable(long, 0)

    assert reason is not None
    message = reason.removeprefix("gateway unreachable: ")
    assert "\n" not in message
    assert len(message) == MAX_MESSAGE
    assert message.endswith("…")


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"is_error": True, "terminal_reason": "api_error", "subtype": "s"}, "api_error"),
        (
            {"is_error": True, "subtype": "error_during_execution", "result": " "},
            "error_during_execution",
        ),
        ({"is_error": True}, "harness reported an error"),
    ],
)
def test_without_result_text_the_message_falls_back(raw: dict[str, object], message: str) -> None:
    assert gateway_unreachable(raw, 0) == GATEWAY_UNREACHABLE.format(message=message)
