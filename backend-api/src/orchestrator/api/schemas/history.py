"""The HTTP shape of `GET /steps` (SPEC CAP-5, FR-25 history).

`HistoryPageOut` is `api/schemas/common.py::Page` with nothing added — the one list envelope,
`{items, next_cursor}` and no second wrapper. `GET /queue` extends `Page` with
`max_active_runs` because its section head reads that figure beside the rows; this section
head reads nothing the rows do not already carry, so it extends nothing.

`cost_usd` is `MoneyStr`: a decimal *string* in USD. A JSON number would be an IEEE double,
and the fraction-of-a-cent difference between a Claude, a Codex and a locally served attempt
is exactly the value that loses digits there — the comparison this whole epic exists for.
A locally served attempt is `"0.000000"` with real token counts beside it (PRD §11), which
is why `cost_usd` being zero and `cost_usd` being absent are different answers here.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from orchestrator.api.schemas.common import MoneyStr, Page, UtcTimestamp
from orchestrator.application.use_cases.history import HistoryPage, HistoryRow


class HistoryRowOut(BaseModel):
    """One executed attempt: the ten columns the table prints, and what they link to.

    `harness`, `model`, `session_id`, the two token counts and `cost_usd` are `null` on a
    non-agent row — a `git.commit` or a `shell` attempt has no harness to name (binding
    rule). `trace_url` is the *Run's* trace and `log_tail_url` is the Run detail read; see
    `application/use_cases/history.py`'s own docstring for why neither is per-attempt.
    """

    attempt_id: UUID
    run_id: UUID
    #: The row's `seq`: `/workflows/{run_id}#step-{seq}` is what a history row links to.
    seq: int
    started_at: UtcTimestamp
    ended_at: UtcTimestamp | None
    seconds: float | None
    project_name: str
    run_label: str
    path: str
    kind: str
    harness: str | None
    model: str | None
    session_id: str | None
    status: str
    token: str
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: MoneyStr | None
    cost_provisional: bool
    trace_url: str | None
    log_tail_url: str

    @classmethod
    def of(cls, row: HistoryRow) -> HistoryRowOut:
        return cls(
            attempt_id=row.attempt_id,
            run_id=row.run_id,
            seq=row.seq,
            started_at=row.started_at,
            ended_at=row.ended_at,
            seconds=row.seconds,
            project_name=row.project_name,
            run_label=row.run_label,
            path=row.path,
            kind=row.kind,
            harness=row.harness,
            model=row.model,
            session_id=row.session_id,
            status=row.status,
            token=row.token,
            tokens_in=row.tokens_in,
            tokens_out=row.tokens_out,
            cost_usd=row.cost_usd,
            cost_provisional=row.cost_provisional,
            trace_url=row.trace_url,
            log_tail_url=row.log_tail_url,
        )


class HistoryPageOut(Page[HistoryRowOut]):
    """`GET /steps`'s body: one page of rows, and the cursor for the page after it."""

    @classmethod
    def of(cls, page: HistoryPage) -> HistoryPageOut:
        return cls(
            items=[HistoryRowOut.of(row) for row in page.items],
            next_cursor=page.next_cursor,
        )
