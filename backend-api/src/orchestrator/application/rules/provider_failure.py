"""CAP-5: a provider credit or rate failure reaches the Operator under its real cause.

An attempt that fails after real work has output tokens, so `harness_failure.gateway_unreachable`
declines it and routing used to name only the exit code. The harness's result object, or the
last lines of its log when the object lacks it, hold what the provider said; this reads it.
Classification is here and nowhere else (AD-10): adapters hand the object over untouched.

**Only an attempt that failed is read, and only what the harness marked as an error.** A
`result` string counts when `is_error` is `true`; an `error` field counts as given; a plain
log line must also say `error`. The agent's own prose, which may discuss rate limits at length,
is never a failure, and a JSON log line that is not an error event is never read as text.

**The message is bounded and scrubbed before it is a park reason.** Read at most `LOG_LINES`
lines of `MAX_LINE` characters, redact anything shaped like a credential, then cut to the
gateway rule's `MAX_MESSAGE`. Redaction comes first so a cut can never leave half a key.
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
    r"\b(?:status|http|error|code)\D{0,12}(?:402|429)\b"
    r"|\b(?:402|429)\s*[:-]?\s*(?:payment required|too many requests|insufficient|credits?)"
    r"|insufficient[ _](?:credits?|funds|quota|balance)"
    r"|\bcredits?\b|credit balance|rate[ _-]?limit|too many requests|payment required"
    r"|exceeded your (?:current )?quota|usage limit",
    re.IGNORECASE,
)
_ERROR_WORD = re.compile(r"error", re.IGNORECASE)
_SECRET = re.compile(
    r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{8,}"
    r"|\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{16,}"
    r"|\bxox[abprs]-[A-Za-z0-9\-]{8,}"
    r"|\bAKIA[0-9A-Z]{12,}"
    r"|(?i:\bBearer\s+\S+)"
    r"|(?i:\b(?:api[_-]?key|token|secret|password|authorization)\b)\s*[:=]\s*(?i:(?:Bearer\s+)?)\S+"
    r"|\b[A-Za-z0-9_\-]{32,}\b"
)


def from_raw(raw: Mapping[str, Any] | None) -> str | None:
    """The park reason when the harness's result object reports a credit or rate failure."""
    if not isinstance(raw, Mapping):
        return None
    text = _error_text(raw)
    return _reason(text) if text is not None and _MARKER.search(text[:MAX_SCAN]) else None


def from_log(lines: Sequence[str]) -> str | None:
    """The park reason from the newest line of the log's tail that reports one."""
    for line in reversed(lines[-LOG_LINES:]):
        text = _log_text(line.strip())
        if text is not None:
            return _reason(text)
    return None


def _log_text(line: str) -> str | None:
    if not line or len(line) > MAX_LINE:
        return None
    if line.startswith("{"):
        try:
            parsed = json.loads(line)
        except ValueError, RecursionError:
            parsed = None
        if isinstance(parsed, Mapping):
            text = _error_text(parsed)
            return text if text is not None and _MARKER.search(text) else None
    return line if _ERROR_WORD.search(line) and _MARKER.search(line) else None


def _error_text(event: Mapping[str, Any]) -> str | None:
    """What a harness event says went wrong, or `None` when it reports no error."""
    result = event.get("result")
    if event.get("is_error") is True and isinstance(result, str):
        return result
    error = event.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, Mapping):
        return _from_error_object(error)
    message = event.get("message")
    if event.get("type") in ERROR_EVENTS and isinstance(message, str):
        return message
    return None


def _from_error_object(error: Mapping[str, Any]) -> str | None:
    """`{message}` or `{data: {message, statusCode}}`; a bare 402 or 429 is named when the
    message itself does not say what it was."""
    data = error.get("data")
    source = data if isinstance(data, Mapping) else error
    message = source.get("message")
    if not isinstance(message, str):
        return None
    status = source.get("statusCode")
    if status in CREDIT_STATUS and not _MARKER.search(message):
        return f"HTTP {status}: {message}"
    return message


def _reason(text: str) -> str:
    collapsed = " ".join(text[:MAX_SCAN].split())
    scrubbed = _SECRET.sub(REDACTED, collapsed)
    if len(scrubbed) > MAX_MESSAGE:
        scrubbed = scrubbed[: MAX_MESSAGE - 1] + "…"
    return PROVIDER_ERROR.format(message=scrubbed)
