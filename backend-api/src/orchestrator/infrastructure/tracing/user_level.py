"""The user-level trace evidence a harness with no trace context at all leaves (AD-11, 7.3).

A sibling of `langfuse_tracer.py` for the reason `tests/unit/test_source_limits.py` makes
checkable, and the same reason 7.2's `session_level.py` is one: that module is at its line
budget, and everything here is one query and the rule for reading its answer.

**What this is evidence of.** `research/tracing.md` §OpenCode: the Langfuse plugin
(`@langfuse/opencode-observability-plugin`) opens one trace per turn, keyed by OpenCode's own
session id, and takes `userId` from the `LANGFUSE_USER_ID` environment variable —
`scripts/harness/opencode.sh` binds that to `ORCH_RUN_ID`, and
`infrastructure/harness/opencode/adapter.py::local_aliases` is what actually sets it. There is
no inbound `TRACEPARENT` (the plugin accepts none, and OpenCode's own native OTLP has no
traceparent support), so nothing this harness sends can be parented under the attempt span this
orchestrator opened, and nothing it sends carries an attempt id either. The Run is the finest
identity available.

**Why a window, and why it is an assumption.** `briefs/7-3-opencode-adapter.md` marks it
`[ASSUMPTION: time-window attribution, since the plugin carries no attempt id]`. A Run can make
several attempts at one row, and every one of them reports the same `userId`; without a window,
a retry's generations would prove the attempt before it observed. The attempt's own
`started_at`/`ended_at` are the only thing that separates them, so a missing bound answers
`False` rather than widening to the whole Run — evidence nobody can attribute is not evidence.

**Why the answer is re-checked.** The query states both halves server-side, and then
`user_level_observed` states them again over what came back. The parameter names are documented
but unobserved (7.4 settles them against the real Langfuse deployment), and a parameter the API
quietly ignored would silently turn "this attempt was observed" into "something of somebody's
was" — which is exactly the class of false green a readiness gate exists to prevent. One
comparison per row is a cheap way to make the assertion true whatever the API does with the
filter.

**Why `local` alone.** `claude` and `codex` are proven by parented spans (AD-10), and `codex`
additionally by 7.2's session-level tag. Offering this rule to either would accept a generation
that merely happened during the attempt as proof the harness's own tracing works.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

log = structlog.get_logger(__name__)

#: The harnesses whose `attempt_observed` may be answered by user-level evidence. One today,
#: and `tests/unit/test_tracer_user_level.py` pins that it is exactly this one and that it does
#: not overlap `SESSION_LEVEL_HARNESSES` — two rules, so neither drifts into the other's harness.
USER_LEVEL_HARNESSES: frozenset[str] = frozenset({"local"})

#: How many of the window's observations are looked at. The query is already narrowed to one
#: user and one attempt's minutes, so this is a ceiling and not a page anything should fill.
USER_OBSERVATION_PAGE_LIMIT = 100

#: The `path` value `attempt_observed` logs when this rule is the one that answered — the third
#: beside `session_level.py`'s `PATH_PARENTED`/`PATH_SESSION`/`PATH_NONE`. It lives here, with
#: the rule it names, so adding a rule and forgetting to make it visible is one edit, not two.
PATH_USER = "user"

#: **Provisional** (addendum §B, 7.4 verifies): the attributes an observation carries the two
#: halves of the rule on, as the SDK's own generated model names them. Constants rather than
#: literals for the same reason every other unobserved name in this epic is one — settling them
#: is one edit each — and read with `getattr`, so a model that names them otherwise answers
#: "not this attempt's" rather than raising.
USER_ID_ATTRIBUTE = "user_id"
START_TIME_ATTRIBUTE = "start_time"

#: Logged (never raised) when the query itself fails: the same degradation the primary query
#: and 7.2's fallback already make, for the same SM-3 reason.
USER_QUERY_FAILED = "langfuse user-level observation query failed; answering not-observed"


def user_level_observed(
    client_ref: Callable[[], Any],
    run_id: UUID,
    *,
    started_at: datetime | None,
    ended_at: datetime | None,
) -> bool:
    """Whether Langfuse holds a generation of this Run inside this attempt's own window.

    The client arrives as the caller's own accessor rather than as a built client, so that
    building it is inside this function's guard too: `LangfuseTracer` constructs its SDK client
    lazily, on first use, and a construction that raises here must degrade exactly like a query
    that raises rather than escaping into a readiness evaluation.

    Never raises (SM-3): a failure answers exactly what a not-yet-observed attempt answers.
    """
    if started_at is None or ended_at is None:
        return False
    try:
        observations = (
            client_ref()
            .api.observations.get_many(
                user_id=str(run_id),
                from_start_time=started_at,
                to_start_time=ended_at,
                limit=USER_OBSERVATION_PAGE_LIMIT,
            )
            .data
            or []
        )
        # inside the guard as well as the query, and deliberately: reading an unobserved API's
        # answer is where a shape nobody has seen yet turns into an exception, and this function
        # promises the same "not observed" for that as for an unreachable Langfuse.
        return any(
            _is_this_attempts(observation, run_id, started_at, ended_at)
            for observation in observations
        )
    except Exception:
        log.exception(USER_QUERY_FAILED, run_id=str(run_id))
        return False


def _is_this_attempts(
    observation: Any, run_id: UUID, started_at: datetime, ended_at: datetime
) -> bool:
    """Both halves of the rule, restated over one returned observation.

    An observation with no `userId` or no `startTime` of its own is rejected rather than given
    the benefit of the doubt: it cannot be shown to be this attempt's, and this function's whole
    job is to decide exactly that.

    A naive timestamp is read as UTC rather than refused. `Attempt.started_at`/`ended_at` are
    always aware (the `Clock` port answers UTC), Langfuse's own API answers UTC, and comparing
    the two directly would raise `TypeError` on a naive one — turning a harness that traced
    perfectly well into an unreadable readiness line, or (before the guard above) into an
    exception inside a readiness evaluation.
    """
    if str(getattr(observation, USER_ID_ATTRIBUTE, None) or "") != str(run_id):
        return False
    started = getattr(observation, START_TIME_ATTRIBUTE, None)
    if not isinstance(started, datetime):
        return False
    return started_at <= _utc(started) <= ended_at


def _utc(moment: datetime) -> datetime:
    """The same instant, always aware — see `_is_this_attempts` for why."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
