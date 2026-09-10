"""The `HistoryQuery` port (SPEC CAP-5, FR-25 history): one page of executed attempts.

Every other read in this system is scoped to one Run, one Project, or the engine's own
holding pen, and each is served by a repository whose unit is a single entity. The Runs
history is not: its unit is the *attempt*, its order spans every Run there has ever been,
and each of its rows needs the attempt, the row it attempted, that row's Run, and that Run's
Project name together. Four repository reads joined in `application/` would page over the
wrong table — an attempt's page is not a Run's page — and would have to read the whole
`attempt` table to find one page of it.

So this is a query port rather than a fifth method on `AttemptRepository`: that port's every
method is keyed by one `step_run_id`, and it already has the one fake this repository allows
it (root `AGENTS.md` hard rule 6). `HistoryEntry` is the join, in domain entities, so
`application/` still never sees a row or a session (AD-2).

**Keyset, not offset.** `HistoryCursor` is `(started_at, attempt_id)` — the exact tuple the
order is on — so a page boundary stays put while new attempts land above it. An `OFFSET`
would slide every later page by one for each attempt started since the first read, which on
this table is a certainty rather than a risk.

**An attempt that never started is not a history row.** `AttemptRepository.mark_started`
writes `started_at` before the harness is awaited (AD-8), so a stored attempt without one is
a row that has not begun. It has no place in an order keyed on `started_at`, and both
implementations drop it rather than inventing a time for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import StepStatus


@dataclass(frozen=True)
class HistoryCursor:
    """Where the previous page stopped: the `(started_at, attempt_id)` of its last row."""

    started_at: datetime
    attempt_id: UUID


@dataclass(frozen=True)
class HistoryQuerySpec:
    """One page's worth of question: the filters, the window, and how many rows to take.

    `statuses` is a tuple of stored `StepStatus` values, never a UI token — mapping the bar's
    `QUE RUN BLK ERR DON` onto them is a rule, and rules live in `application/`. `None` means
    "every status", which is not the same as the empty tuple ("no status", which matches
    nothing); both are reachable and they are told apart on purpose.
    """

    limit: int
    project_id: UUID | None = None
    statuses: tuple[StepStatus, ...] | None = None
    harness: str | None = None
    after: HistoryCursor | None = None


@dataclass(frozen=True)
class HistoryEntry:
    """One executed attempt, joined with the row, the Run and the Project name it belongs to.

    `project_name` rather than the whole `Project`: the table prints a name and nothing else
    of it, and carrying the entity would make this port's answer depend on a second
    entity's shape for one column.
    """

    attempt: Attempt
    step: StepRun
    run: Run
    project_name: str


@runtime_checkable
class HistoryQuery(Protocol):
    """One page of executed attempts, newest first. A read; it writes nothing."""

    def list_attempts(self, spec: HistoryQuerySpec) -> list[HistoryEntry]:
        """At most `spec.limit` entries matching `spec`, ordered `started_at desc, id desc`,
        starting strictly after `spec.after` when one is given."""
        ...
