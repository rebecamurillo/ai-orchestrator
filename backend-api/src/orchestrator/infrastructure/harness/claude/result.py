"""Reading a `claude -p --output-format json` run back out of its own log (AD-10).

Split out of `adapter.py` because the two things are different: that module writes the
invocation, this one reads what came back, and only this one is tolerant by design. The log
holds stdout and stderr interleaved — npm warnings, an OTLP exporter's errors and the
harness's own result envelope all share the file — so every function here answers "nothing
this system could read" rather than raising, and `usage_from` reports `None` for a result
that is present but not a number. Nothing inside the envelope is interpreted; `raw_result`
carries the object on whole, and 5.7 reads the budget-cap field out of it.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from orchestrator.domain.ports.harness import HarnessUsage

#: The envelope field `claude -p --output-format json` puts on its own final object, and the
#: value that marks it. Reading it is the same class of read as `session_id` — the harness's
#: own framing, not anything the model produced (AD-10).
RESULT_TYPE_FIELD = "type"
RESULT_TYPE = "result"

#: The one encoding every log and prompt file is written and read in, so the container's
#: locale never decides what is parsed out of an attempt's own record.
ENCODING = "utf-8"


def read_text(log_path: Path) -> str:
    """The log's text, or nothing at all — a process killed before it wrote has no log."""
    if not log_path.is_file():
        return ""
    return log_path.read_text(encoding=ENCODING, errors="replace")


def json_objects(text: str) -> list[dict[str, Any]]:
    """Every top-level JSON object in `text`, in the order they appear.

    Scanning rather than `json.loads`: the log holds stdout and stderr interleaved, so the
    result object is normally surrounded by whatever the tooling printed. Each `{` is
    offered to `raw_decode`, and a successful decode advances past the whole object, so a
    nested one is never mistaken for a top-level one.
    """
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    index = text.find("{")
    while index != -1:
        try:
            value, end = decoder.raw_decode(text, index)
        except ValueError:
            index = text.find("{", index + 1)
            continue
        found.append(value)
        index = text.find("{", end)
    return found


def result_object(text: str) -> dict[str, Any] | None:
    """The harness's own result object, or `None` when the log holds no JSON at all.

    The brief's rule is "the last JSON object", and that is the fallback here rather than
    the rule, because stdout and stderr share one file: an OTLP exporter error or an npm
    error payload printed *after* the result would take its place, and `usage` would go
    `None` on a run that reported it. So the last object carrying `"type": "result"` wins.

    That is not an interpretation of model output (AD-10). `type` is the envelope field
    `--output-format json` puts on the object it prints — the same class of read as
    `session_id`, which this adapter already takes from the harness's own framing. Nothing
    inside the envelope is read here; `raw_result` carries it on whole.
    """
    objects = json_objects(text)
    envelopes = [item for item in objects if item.get(RESULT_TYPE_FIELD) == RESULT_TYPE]
    if envelopes:
        return envelopes[-1]
    return objects[-1] if objects else None


def _as_int(value: Any) -> int | None:
    """A token count, or `None` when the field is there but is not one.

    `bool` is rejected explicitly because it is an `int` in Python, and `True` tokens is a
    reading error rather than one token.
    """
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _as_decimal(value: Any) -> Decimal | None:
    """A USD amount, or `None` when the field is there but is not one."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def usage_from(result: dict[str, Any] | None) -> HarnessUsage | None:
    """The three numbers AD-11 records, or `None` when the result does not carry all three.

    Nothing is inferred and nothing raises. A result with a cost and no token counts is as
    unusable as no result at all, because `attempt.tokens_in`/`tokens_out` would then be
    written as zero and read as measured; a field that is present but not a number
    (`"total_cost_usd": "n/a"`) is the same fact, and is reported the same way rather than
    as an exception a walker would have to catch. `raw_result` still carries the object, so
    nothing observed is lost.
    """
    if result is None:
        return None
    usage = result.get("usage")
    if not isinstance(usage, dict):
        return None
    cost = _as_decimal(result.get("total_cost_usd"))
    tokens_in = _as_int(usage.get("input_tokens"))
    tokens_out = _as_int(usage.get("output_tokens"))
    if cost is None or tokens_in is None or tokens_out is None:
        return None
    return HarnessUsage(tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost)
