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

from typing import Any

from orchestrator.domain.ports.harness import HarnessUsage
from orchestrator.infrastructure.harness.jsonl import (
    ENCODING,
    as_decimal,
    as_int,
    json_objects,
    objects_with,
    read_text,
)

#: What this module still owns, plus what it re-exports from `jsonl.py`. The tolerant
#: primitives moved there in 7.1, when `codex/` needed the same four; every name this module
#: was reachable under stays reachable here, because `adapter.py`, `fake/adapter.py` and
#: `tests/unit/test_claude_result_parsing.py` all import them from this path.
__all__ = [
    "ENCODING",
    "RESULT_TYPE",
    "RESULT_TYPE_FIELD",
    "json_objects",
    "read_text",
    "result_object",
    "usage_from",
]

#: The envelope field `claude -p --output-format json` puts on its own final object, and the
#: value that marks it. Reading it is the same class of read as `session_id` — the harness's
#: own framing, not anything the model produced (AD-10).
RESULT_TYPE_FIELD = "type"
RESULT_TYPE = "result"


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
    envelopes = objects_with(objects, RESULT_TYPE_FIELD, RESULT_TYPE)
    if envelopes:
        return envelopes[-1]
    return objects[-1] if objects else None


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
    cost = as_decimal(result.get("total_cost_usd"))
    tokens_in = as_int(usage.get("input_tokens"))
    tokens_out = as_int(usage.get("output_tokens"))
    if cost is None or tokens_in is None or tokens_out is None:
        return None
    return HarnessUsage(tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost)
