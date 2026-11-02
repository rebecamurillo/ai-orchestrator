"""CAP-5: a provider credit or rate failure reaches the Operator under its real cause.

An attempt that fails after real work has output tokens, so `harness_failure.gateway_unreachable`
declines it and routing would name only the exit code. The harness's result object, or the
last lines of its log when the object lacks it, hold what the provider said; this reads it.
Classification is here and nowhere else (AD-10): adapters hand the object over untouched.

**Only an attempt that failed is read, and only what the harness marked as an error.** A
`result` or `errors` list counts when `is_error` is `true`; an `error` or `message` field
counts only on an `error` or `turn.failed` event, so a retried request (`api_retry` carries
`error`) is no failure. A plain log line must also say `error`, and JSON after a prefix is an
event only when it has a `type`. The agent's own prose, which may discuss rate limits at
length, is never a failure.

**The message is bounded and scrubbed before it is a park reason.** `result` text bypasses the
log reader's own scrub, so credentials are redacted here (hard rule 5): names carry any prefix,
values may be quoted, and `Bearer` and `Basic` schemes are covered. Read at most `LOG_LINES`
lines of `MAX_LINE` characters, redact, then cut to the gateway rule's `MAX_MESSAGE`; redaction
comes first so a cut can never leave half a key.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from orchestrator.application.rules.harness_failure import MAX_MESSAGE

PROVIDER_ERROR = "provider error: {message}"
#: Lines of the log tail examined, and the longest line worth parsing; a longer one is tool
#: output, not a provider's error.
LOG_LINES = 40
MAX_LINE = 8000
#: Characters of one message examined for a marker.
MAX_SCAN = 4000

CREDIT_STATUS = (402, 429)
ERROR_EVENTS = ("error", "turn.failed")
REDACTED = "[redacted]"

_MARKER = re.compile(
    r"\b(?:status(?:[_ ]?code)?|http|error)[\"']?[\s:=(]{0,3}(?:402|429)\b"
    r"|insufficient[ _](?:credits?|funds|quota|balance)"
    r"|out of credits|no credits|credits? (?:exhausted|balance)"
    r"|rate[ _-]?limit|too many requests|payment required"
    r"|exceeded your (?:current )?quota|quota (?:has been )?exceeded"
    r"|budget (?:has been )?exceeded|usage limit|spend limit|hit your (?:\w+ ){0,2}limit",
    re.IGNORECASE,
)
#: Telemetry exporters report the same HTTP statuses; they are not the provider's.
_NOISE = re.compile(r"otlp|opentelemetry|exporter|langfuse", re.IGNORECASE)
_ERROR_WORD = re.compile(r"error", re.IGNORECASE)
_SECRET = re.compile(
    r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{8,}"
    r"|\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{16,}"
    r"|\bxox[abprs]-[A-Za-z0-9\-]{8,}"
    r"|\bAKIA[0-9A-Z]{12,}"
    r"|(?i:\bBearer\s+)[^\s\"',}]+"
    r"|(?i:[A-Za-z0-9_\-]*(?:api[_-]?key|token|secret|passw(?:or)?d|authorization))"
    r"[\"']?\s*[:=]\s*[\"']?(?i:(?:Bearer|Basic)\s+)?[^\s\"',}]+"
    r"|\b[A-Za-z0-9_\-]{32,}\b"
)


def from_raw(raw: Mapping[str, Any] | None) -> str | None:
    """The park reason when the harness's result object reports a credit or rate failure."""
    if not isinstance(raw, Mapping):
        return None
    text = _error_text(raw)
    return _reason(text) if text is not None and _reports(text) else None


def from_log(lines: Sequence[str]) -> str | None:
    """The park reason from the newest line of the log's tail that reports one."""
    for line in reversed(lines[-LOG_LINES:]):
        text = _log_text(line.strip())
        if text is not None:
            return _reason(text)
    return None


def _reports(text: str) -> bool:
    scanned = text[:MAX_SCAN]
    return _MARKER.search(scanned) is not None and _NOISE.search(scanned) is None


def _log_text(line: str) -> str | None:
    if not line or len(line) > MAX_LINE:
        return None
    event = _event_in(line)
    if event is not None:
        text = _error_text(event)
        return text if text is not None and _reports(text) else None
    return line if _ERROR_WORD.search(line) and _reports(line) else None


def _event_in(line: str) -> Mapping[str, Any] | None:
    """The JSON event a line carries: the whole line, or what follows a prefix when that is
    an object with a `type`."""
    start = line.find("{")
    if start < 0:
        return None
    try:
        parsed = json.loads(line[start:])
    except ValueError, RecursionError:
        return None
    if isinstance(parsed, dict) and (start == 0 or "type" in parsed):
        return parsed
    return None


def _error_text(event: Mapping[str, Any]) -> str | None:
    """What a harness event says went wrong, or `None` when it reports no error."""
    if event.get("is_error") is True:
        return _failed_result(event)
    if event.get("type") not in ERROR_EVENTS:
        return None
    error = event.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, Mapping):
        return _from_error_object(error)
    message = event.get("message")
    return message if isinstance(message, str) else None


def _failed_result(event: Mapping[str, Any]) -> str | None:
    result = event.get("result")
    if isinstance(result, str):
        return result
    errors = event.get("errors")
    texts = [each for each in errors if isinstance(each, str)] if isinstance(errors, list) else []
    return " ".join(texts) or None


def _from_error_object(error: Mapping[str, Any]) -> str | None:
    """`{message}` or `{data: {message, statusCode}}`; a bare 402 or 429 is named when the
    message itself does not say what it was."""
    data = error.get("data")
    source = data if isinstance(data, Mapping) else error
    message = source.get("message")
    if not isinstance(message, str):
        return None
    status = source.get("statusCode")
    if status in CREDIT_STATUS and not _reports(message):
        return f"HTTP {status}: {message}"
    return message


def _reason(text: str) -> str:
    collapsed = " ".join(text[:MAX_SCAN].split())
    scrubbed = _SECRET.sub(REDACTED, collapsed)
    if len(scrubbed) > MAX_MESSAGE:
        scrubbed = scrubbed[: MAX_MESSAGE - 1] + "…"
    return PROVIDER_ERROR.format(message=scrubbed)
