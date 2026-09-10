"""`list_history` (SPEC CAP-5, FR-25 history): every execution of every step, newest first.

`GET /steps` answers the one question the three-harness design exists to make answerable:
what has actually run, on which harness, for how long and at what cost — across every Run
rather than inside one. One row per *attempt*, so a row retried three times reads as three
lines and the comparison is a scroll rather than a query (SM-3).

**Nothing here derives a status** (AD-8). `status` is the attempt's own stored status — the
status the row reached *through this attempt* (`domain/entities/attempt.py`) — and `token` is
`application/graph.py::STEP_TOKENS`'s existing mapping of it, the same table the Steps table
and the run graph read. This module states what it read; `apply_step_result` and `signal_run`
remain the only writers.

**The status filter maps UI tokens onto stored statuses.** The Runs bar offers
`ALL · QUE · RUN · BLK · ERR · DON` (UX-DR14), which was written for *Run* statuses; an
attempt's alphabet is the eight-token `StepStatus` one. `STATUS_FILTERS` below is that
mapping, and it is deliberately not a partition: `BLK` is the brief's own "attempts whose row
ended `blocked` or `error`" — the two ways a row stops short — and `ERR` narrows to the
errored ones alone. Two gaps follow, and they are gaps rather than bugs: the bar offers no
`CHK` and no `SKP`, so a `checkpoint` or `skipped` attempt is reachable only through no
filter at all.

**Two fields the brief names have no fully faithful referent, and say so rather than
inventing one:**

- `trace_url` is the *Run's* trace, not the attempt's. Nothing stores a per-attempt trace id
  — `domain/entities/attempt.py` has no such column and `Tracer.trace_url` takes a trace id —
  so the honest link is the one trace that does exist (`Run.trace_id`, opened once by
  `create_run`). A per-attempt link would have to be derived from something unstored.
- `log_tail_url` is `GET /runs/{run_id}/detail`, because that read is the only thing in this
  system that serves an attempt's log tail (`StepRowOut.latest.log_tail`, read through the
  `Logs` port). **No per-attempt log resource is served**: the brief names one that does not
  exist, and this story's own Scope is "Out: nothing else", so the field points at the read
  that does answer rather than at a route nobody would serve.
"""

from __future__ import annotations

import binascii
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.application.graph import STEP_TOKENS
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Invalid
from orchestrator.domain.ports.history import (
    HistoryCursor,
    HistoryEntry,
    HistoryQuery,
    HistoryQuerySpec,
)
from orchestrator.domain.ports.tracer import Tracer
from orchestrator.domain.statuses import StepStatus

#: The page size the brief names, and the one `GET /steps` uses when none is asked for.
DEFAULT_LIMIT = 50

#: The bar's status tokens (UX-DR14), each as the stored statuses it selects. See the module
#: docstring for why `BLK` and `ERR` overlap and why `CHK`/`SKP` are not offered.
STATUS_FILTERS: dict[str, tuple[StepStatus, ...]] = {
    "QUE": ("planned", "queued"),
    "RUN": ("running",),
    "BLK": ("blocked", "error"),
    "ERR": ("error",),
    "DON": ("done",),
}

#: What separates the two halves of an encoded cursor. `datetime.isoformat()` never emits it
#: and a UUID never contains it, so splitting on it is unambiguous.
_CURSOR_SEPARATOR = "|"


@dataclass(frozen=True)
class HistoryPorts:
    """What `list_history` reads: the query, and a tracer for the Run's own trace link.

    `tracer` is optional for the reason `RunViewPorts.tracer` is (`use_cases/run_views.py`):
    a read wired without one publishes no trace link rather than failing.
    """

    history: HistoryQuery
    tracer: Tracer | None = None


@dataclass(frozen=True)
class HistoryFilters:
    """What one request asks for: the bar's two filters, the harness, the window, the size.

    A bundle rather than five keyword arguments, because five plus the ports is one more
    than ruff's `PLR0913` allows and because the router already parses them as a set.
    `status` is a UI token here — `STATUS_FILTERS` maps it — and `cursor` is the opaque
    token a previous page issued.
    """

    project_id: UUID | None = None
    status: str | None = None
    harness: str | None = None
    cursor: str | None = None
    limit: int = DEFAULT_LIMIT


@dataclass(frozen=True)
class HistoryRow:
    """One executed attempt, as the HISTORY table prints it."""

    attempt_id: UUID
    run_id: UUID
    #: The row's `seq`, so the link can be `/workflows/{run_id}#step-{seq}` from this read
    #: alone. The brief's field list omits it and its own link rule needs it.
    seq: int
    started_at: datetime
    ended_at: datetime | None
    seconds: float | None
    project_name: str
    run_label: str
    path: str
    kind: str
    harness: str | None
    model: str | None
    session_id: str | None
    status: StepStatus
    token: str
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: Decimal | None
    cost_provisional: bool
    trace_url: str | None
    log_tail_url: str


@dataclass(frozen=True)
class HistoryPage:
    """One page of the history: its rows, and where the next page would start."""

    items: list[HistoryRow]
    next_cursor: str | None


def list_history(ports: HistoryPorts, filters: HistoryFilters | None = None) -> HistoryPage:
    """One page of executed attempts, newest first, and the cursor for the page after it.

    **A full page always carries a cursor; a short one never does.** That is the brief's own
    acceptance — ten rows read as `limit=5` twice, then "the third page is empty with
    `next_cursor null`" — and it costs one read that a look-ahead of `limit + 1` rows would
    save. The trade is deliberate: a look-ahead makes *every* page pay for a row it discards,
    while this shape makes only a history whose length divides exactly by the page size pay
    for one empty read at the end of it. The visible consequence is that the *more* control
    survives one click past the end and then goes away, which is a fact about the data
    rather than an error to report.

    An attempt with no `started_at` is dropped rather than printed. Both implementations of
    the port already exclude one (`domain/ports/history.py`), so this is the guard that
    keeps that promise checkable from this side rather than assumed: a row in the history is
    an execution, and an attempt that never started has no time to file itself under.
    """
    asked = filters or HistoryFilters()
    spec = HistoryQuerySpec(
        limit=asked.limit,
        project_id=asked.project_id,
        statuses=_statuses(asked.status),
        harness=asked.harness,
        after=decode_cursor(asked.cursor),
    )
    entries = ports.history.list_attempts(spec)
    page = [(entry, at) for entry in entries if (at := entry.attempt.started_at) is not None]
    return HistoryPage(
        items=[_row(ports, entry, at) for entry, at in page],
        next_cursor=encode_cursor(entries[-1]) if len(entries) == asked.limit else None,
    )


def _statuses(status: str | None) -> tuple[StepStatus, ...] | None:
    """The stored statuses one UI token selects; `None` for no filter at all."""
    if status is None:
        return None
    if status not in STATUS_FILTERS:
        offered = " ".join(sorted(STATUS_FILTERS))
        raise Invalid(f"status must be one of {offered}, got {status!r}")
    return STATUS_FILTERS[status]


def encode_cursor(entry: HistoryEntry) -> str:
    """`(started_at, attempt_id)` as one opaque base64 token — the brief's own cursor.

    Read off the last entry the *port* answered, not the last row printed: the two differ
    only for an attempt with no `started_at`, and a cursor built from a printed row would
    then re-read the one that was dropped on every later page. `started_at` falling back to
    `run.created_at` is that one case — the window has to move past the entry either way,
    and the Run's own creation is the only time such an attempt is known to be after.
    """
    started_at = entry.attempt.started_at or entry.run.created_at
    raw = f"{started_at.isoformat()}{_CURSOR_SEPARATOR}{entry.attempt.id}"
    return urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str | None) -> HistoryCursor | None:
    """The window a cursor names, or `None` for the first page.

    Every way a cursor can be wrong is one refusal, because the caller cannot act on which:
    a cursor is opaque, so a client that did not get this one from a previous page has
    nothing to correct. Refusing rather than ignoring it matters — silently reading page one
    for a broken page-three cursor is a *more* control that never reaches the end.
    """
    if cursor is None:
        return None
    try:
        raw = urlsafe_b64decode(cursor.encode()).decode()
        started_at, attempt_id = raw.split(_CURSOR_SEPARATOR)
        return HistoryCursor(
            started_at=datetime.fromisoformat(started_at), attempt_id=UUID(attempt_id)
        )
    except (ValueError, binascii.Error, UnicodeDecodeError) as error:
        raise Invalid(f"cursor is not one this endpoint issued: {cursor!r}") from error


def _row(ports: HistoryPorts, entry: HistoryEntry, started_at: datetime) -> HistoryRow:
    """One joined entry as the table's own row. Reads statuses; derives none (AD-8)."""
    attempt, step, run = entry.attempt, entry.step, entry.run
    return HistoryRow(
        attempt_id=attempt.id,
        run_id=run.id,
        seq=step.seq,
        started_at=started_at,
        ended_at=attempt.ended_at,
        seconds=_seconds(started_at, attempt.ended_at),
        project_name=entry.project_name,
        run_label=run_label(run),
        path=step.path,
        kind=step.kind,
        harness=attempt.harness,
        model=attempt.model,
        session_id=attempt.session_id,
        status=attempt.status,
        token=STEP_TOKENS[attempt.status],
        tokens_in=attempt.tokens_in,
        tokens_out=attempt.tokens_out,
        cost_usd=attempt.cost_usd,
        cost_provisional=attempt.cost_provisional,
        trace_url=_trace_url(ports, run),
        log_tail_url=f"/api/v1/runs/{run.id}/detail",
    )


def _seconds(started_at: datetime, ended_at: datetime | None) -> float | None:
    """How long this attempt took, or `None` while it is still in flight."""
    return None if ended_at is None else (ended_at - started_at).total_seconds()


def run_label(run: Run) -> str:
    """`{template} v{n} · {branch}` — the `workflow` cell (binding rule).

    A local function rather than an import of `application/preflight/checks.py::run_label`,
    which answers a different question (`{template} · {branch}`, with no version, for the
    sentence naming a Run that holds a lock). The same small local duplication
    `use_cases/queue.py::_next_step_label` documents for its own two-caller helper.
    """
    branch = str(run.inputs.get("base_branch") or run.inputs.get("branch") or "")
    return f"{run.template_name} v{run.template_version} · {branch}"


def _trace_url(ports: HistoryPorts, run: Run) -> str | None:
    """The Run's Langfuse link — see the module docstring for why it is not the attempt's."""
    if ports.tracer is None or not run.trace_id:
        return None
    return ports.tracer.trace_url(run.trace_id)
