"""O-5: a harness that never reached its model is a network problem, not a Story problem.

A result object that says `is_error` and an attempt that produced no output tokens means the
gateway (or the provider behind it) could not be reached; the Story file is untouched, so
routing on it would point the Operator at a `draft` file instead. The caller routes the reason
through the row's `retry` exactly as it does for `unexpected status`, and a cap stop
(`error_max_budget_usd`) is the budget rule's, never this one's.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

GATEWAY_UNREACHABLE = "gateway unreachable: {message}"
MAX_MESSAGE = 200
CAP_SUBTYPE = "error_max_budget_usd"


def gateway_unreachable(raw: Mapping[str, Any] | None, tokens_out: int | None) -> str | None:
    """The park reason for an infrastructure failure, or `None` when the result is not one."""
    if not isinstance(raw, Mapping) or raw.get("is_error") is not True:
        return None
    if raw.get("subtype") == CAP_SUBTYPE or tokens_out:
        return None
    return GATEWAY_UNREACHABLE.format(message=_message(raw))


def _message(raw: Mapping[str, Any]) -> str:
    text = raw.get("result")
    if not isinstance(text, str) or not text.strip():
        text = str(raw.get("terminal_reason") or raw.get("subtype") or "harness reported an error")
    text = " ".join(text.split())
    return text if len(text) <= MAX_MESSAGE else text[: MAX_MESSAGE - 1] + "…"
