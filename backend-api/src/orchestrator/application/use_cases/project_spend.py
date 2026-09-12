"""`project_metrics` (story 8-6): per-project monthly spend and run-status counts.

One `runs.list(project_id=...)` call per request computes all four metrics without a second
repository round trip. Returns a frozen `ProjectMetrics` dataclass so callers can destructure
the four values independently without risking mutation.

`monthly_spend_usd` covers only Runs whose `started_at` falls in the same calendar month as
`now`. A Run that was queued but never started (`started_at is None`) is excluded — it
contributed no compute cost yet.

`monthly_spend_provisional` is `True` when any Run in the monthly sum carries
`spend_provisional=True` — the flag `record_attempt_spend` maintains in its own pass.

`needs_you_count` counts ALL Runs for the project with `status == "needs_you"`, with no time
window — a parked Run from three months ago still needs operator attention.

`failed_recent_count` counts Runs with `status == "failed"` and a reference timestamp
(`ended_at or created_at`) within the last 7 days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from orchestrator.domain.ports.repositories import RunRepository

_ZERO = Decimal("0")
_RECENT_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class ProjectMetrics:
    """All four per-project metrics, derived in one pass over `runs.list(project_id=...)`."""

    monthly_spend_usd: str
    monthly_spend_provisional: bool
    needs_you_count: int
    failed_recent_count: int


def project_metrics(
    runs: RunRepository | None,
    project_id: UUID,
    now: datetime,
) -> ProjectMetrics:
    """Compute the four project metrics from the live run list.

    Returns zero-valued `ProjectMetrics` when `runs` is `None` (test harnesses predating
    SPEC CAP-6, or callers that have not wired the repository yet).
    """
    if runs is None:
        return ProjectMetrics(
            monthly_spend_usd="0.00",
            monthly_spend_provisional=False,
            needs_you_count=0,
            failed_recent_count=0,
        )

    month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    cutoff = now - _RECENT_WINDOW

    monthly_total = _ZERO
    monthly_provisional = False
    needs_you = 0
    failed_recent = 0

    for run in runs.list(project_id=project_id):
        # monthly spend — only runs that have actually started this calendar month
        if run.started_at is not None and run.started_at >= month_start:
            monthly_total += run.spend_usd
            if run.spend_provisional:
                monthly_provisional = True

        # needs_you — all time, no window
        if run.status == "needs_you":
            needs_you += 1

        # failed recent — 7-day window using ended_at then created_at as fallback
        if run.status == "failed":
            reference = run.ended_at or run.created_at
            if reference >= cutoff:
                failed_recent += 1

    return ProjectMetrics(
        monthly_spend_usd=f"{monthly_total:.2f}",
        monthly_spend_provisional=monthly_provisional,
        needs_you_count=needs_you,
        failed_recent_count=failed_recent,
    )
