"""Reading an `opencode run --format json` run back out of its own event stream (AD-10, AD-11).

Split from `adapter.py` for the reason `codex/events.py` is: that module writes the invocation,
this one reads what came back, and only this one is tolerant by design. The two facts this
system needs are in two different places, exactly as they are for Codex:

- the **session**, which OpenCode names itself (`capabilities.preassign_session = False`). It
  is the id the Langfuse plugin keys its own trace by (`research/tracing.md` §OpenCode) and the
  id `opencode run --session` would continue, so it is worth recording even though this harness
  declares no resume. A stream that never printed one is not an error: `adapter.py` then asks
  the session store, and an attempt that has neither is reported with `session_id = None`.
- the **usage**, tokens only. The cost is `STREAM_COST_USD` and — unlike Codex, where zero
  means "the Gateway settles it" — here zero is the *answer*: PRD §11 records a model served on
  the host at cost `0` with its tokens, which is what makes `local` a measurable cost lever
  rather than a blank. `agent_tail.usage` still marks the figure `cost_provisional` until the
  Gateway's own spend rows arrive, and those rows carry `spend 0` too.

**Every harness-native name in this module is provisional** (`briefs/7-3-opencode-adapter.md`,
addendum §B). The field names are the documented shape and were not observed: this story never
runs the CLI, and story 7.4 is where they are settled on the real host at `OPENCODE_VERSION`.
They are constants rather than literals so that settling them is one edit each, and the
behaviour around them — absent is `None`, partial is `None`, the object is handed on whole —
holds whatever they turn out to be.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from orchestrator.domain.ports.harness import HarnessUsage
from orchestrator.infrastructure.harness.jsonl import as_int, json_objects

#: **Provisional** (addendum §B, 7.4 verifies): the field every event of an OpenCode stream
#: carries its session on. OpenCode spells it in camel case — it is the same id its own
#: `--session` flag takes — so it is stated here once rather than guessed at each read.
SESSION_ID_FIELD = "sessionID"

#: **Provisional** (addendum §B, 7.4 verifies): the envelope a finished message reports its
#: token counts in, and the two fields inside it this system records. OpenCode's message shape
#: carries more (`reasoning`, `cache.read`, `cache.write`); AD-11 stores two numbers, so the
#: rest is left in `raw_result` rather than summed into something nobody asked for.
TOKENS = "tokens"
INPUT_TOKENS = "input"
OUTPUT_TOKENS = "output"

#: What a model served on the host costs (PRD §11). **Not provisional**, and not the same
#: statement Codex's identically-valued constant makes: this is the recorded figure, not a
#: placeholder for one the Gateway will replace. The Gateway's own rows for these models carry
#: `spend 0` as well, so the settled figure agrees with it.
STREAM_COST_USD = Decimal("0")


def events(text: str) -> list[dict[str, Any]]:
    """The stream's events, read out of a log that also holds stderr.

    `json_objects` and not a line split, deliberately: the OpenCode CLI shares this file with
    npm's own warnings and with the plugin's exporter, so an event can arrive with something
    glued to the front of its line.
    """
    return json_objects(text)


def session_id_from(stream: list[dict[str, Any]]) -> str | None:
    """The session this attempt ran under, or `None` when the stream never named one.

    The *first* such event wins, the same rule `codex/events.py` follows: OpenCode reports the
    session on every event of the turn, so a stream holds the same id many times, and taking
    the first is what keeps the recorded id stable if a later event ever carried a different
    one.

    `None` is an ordinary outcome, not a failure — `adapter.py` asks the session store next.
    """
    for event in stream:
        value = event.get(SESSION_ID_FIELD)
        if isinstance(value, str) and value:
            return value
    return None


def result_object(stream: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The last event that reported tokens, or the last object of any kind, or `None`.

    The fallback is only a fallback, and the order matters for the same reason it does in
    `codex/events.py`: the Langfuse plugin and the OTLP exporter both print their own JSON when
    they shut down, *after* the turn ended, and taking whatever printed last would report
    `usage = None` on a run that reported usage.

    Nothing inside it is interpreted (AD-10); `HarnessResult.raw_result` carries it whole.
    """
    reported = [event for event in stream if isinstance(event.get(TOKENS), dict)]
    if reported:
        return reported[-1]
    return stream[-1] if stream else None


def usage_from(result: dict[str, Any] | None) -> HarnessUsage | None:
    """The tokens the harness reported, or `None` when it did not report both.

    Both, or neither: `attempt.tokens_in`/`tokens_out` written as zero would be read back as
    measured, and for this harness that mistake is invisible — the cost is legitimately zero,
    so a zero-token record would look like an ordinary cheap attempt rather than a missing one.
    """
    if result is None:
        return None
    tokens = result.get(TOKENS)
    if not isinstance(tokens, dict):
        return None
    tokens_in = as_int(tokens.get(INPUT_TOKENS))
    tokens_out = as_int(tokens.get(OUTPUT_TOKENS))
    if tokens_in is None or tokens_out is None:
        return None
    return HarnessUsage(tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=STREAM_COST_USD)
