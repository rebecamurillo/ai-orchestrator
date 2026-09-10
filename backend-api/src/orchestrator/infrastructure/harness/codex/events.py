"""Reading a `codex exec --json` run back out of its own event stream (AD-10, AD-11).

Split from `adapter.py` for the reason `claude/result.py` is: that module writes the
invocation, this one reads what came back, and only this one is tolerant by design. What
differs is the shape — Claude Code prints one result envelope at the end, Codex prints an
*event per line* — so the two facts this system needs are in two different places:

- the **session**, which is the `thread.started` event's own id. It is not in the argv, because
  Codex names its own thread (`capabilities.preassign_session = False`); the stream is the only
  place it exists, and a stream that never printed the event leaves the attempt with no session
  and 7.2's `session id recorded` readiness line failing. That is a reported fact, never an
  exception.
- the **usage**, from the final `turn.completed` event. Tokens only: Codex's own stream reports
  no money at all, so `cost_usd` is zero here and AD-11's Gateway spend — recorded against this
  attempt's `x-litellm-session-id` header — is the figure that settles it. `agent_tail.usage`
  marks every harness figure `cost_provisional`, which is exactly what this one is.

**Every name in this module is provisional** (`briefs/7-1-codex-adapter.md`, addendum §B). The
event names and their fields are the documented shape and were not observed: this story never
runs the CLI, and story 7.2 is where they are settled on the real host. They are constants
rather than literals so that settling them is one edit each, and the behaviour around them —
absent is `None`, partial is `None`, the object is handed on whole — holds whatever they turn
out to be.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from orchestrator.domain.ports.harness import HarnessUsage
from orchestrator.infrastructure.harness.jsonl import as_int, json_objects, objects_with

#: The envelope field every event of the stream carries.
EVENT_TYPE = "type"
#: **Provisional** (addendum §B, 7.2 verifies): the event that opens a thread, and the field on
#: it that names the thread. `session_id_from` reads nothing else out of the stream.
THREAD_STARTED = "thread.started"
THREAD_ID = "thread_id"
#: **Provisional** (addendum §B, 7.2 verifies): the event that ends a turn, and the envelope on
#: it that carries the token counts.
TURN_COMPLETED = "turn.completed"
USAGE = "usage"
INPUT_TOKENS = "input_tokens"
OUTPUT_TOKENS = "output_tokens"

#: What this harness's own stream says an attempt cost: nothing, because it reports tokens and
#: no money. AD-11 replaces it with the Gateway's settled spend, and `cost_provisional` is what
#: says the replacement has not happened yet.
STREAM_COST_USD = Decimal("0")


def events(text: str) -> list[dict[str, Any]]:
    """The stream's events, read out of a log that also holds stderr.

    `json_objects` and not a line split, deliberately: a warning printed onto the front of a
    line would swallow the event on it, and the two streams share this file by construction.
    """
    return json_objects(text)


def session_id_from(stream: list[dict[str, Any]]) -> str | None:
    """The thread this attempt ran under, or `None` when the stream never named one.

    The *first* such event wins. A resumed turn reopens the thread it was given, so a stream
    holding two of them holds the same id twice; taking the first is what keeps that true even
    if a later event ever carried a different one, since the id the attempt is recorded under
    must be the one the caller can resume.
    """
    for event in objects_with(stream, EVENT_TYPE, THREAD_STARTED):
        value = event.get(THREAD_ID)
        if isinstance(value, str) and value:
            return value
    return None


def result_object(stream: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The turn's own completion event, or `None` when the stream holds no JSON at all.

    The last `turn.completed` wins, and the last object of any kind is only the fallback — the
    same rule `claude/result.py` follows and for the same reason: an OTLP exporter that fails
    on shutdown prints its own JSON *after* the turn ended, and taking whatever printed last
    would report `usage = None` on a run that reported usage.

    Nothing inside it is interpreted (AD-10); `HarnessResult.raw_result` carries it whole.
    """
    completed = objects_with(stream, EVENT_TYPE, TURN_COMPLETED)
    if completed:
        return completed[-1]
    return stream[-1] if stream else None


def usage_from(result: dict[str, Any] | None) -> HarnessUsage | None:
    """The tokens the harness reported, or `None` when it did not report both.

    Both, or neither: `attempt.tokens_in`/`tokens_out` written as zero would be read back as
    measured, which is the one thing AD-11 does not allow a missing figure to become. The cost
    is `STREAM_COST_USD` — see this module's docstring; it is the Gateway's to settle, not the
    stream's to state.
    """
    if result is None:
        return None
    usage = result.get(USAGE)
    if not isinstance(usage, dict):
        return None
    tokens_in = as_int(usage.get(INPUT_TOKENS))
    tokens_out = as_int(usage.get(OUTPUT_TOKENS))
    if tokens_in is None or tokens_out is None:
        return None
    return HarnessUsage(tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=STREAM_COST_USD)
