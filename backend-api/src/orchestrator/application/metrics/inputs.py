"""What every part A method reads: one Run's rows, attempts, facts, reads and records.

Built by `live.load_inputs` (or by a test); the methods never read a repository.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from orchestrator.application.use_cases.spend_figures import StoredRead, harness_money
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts, FactSet, UsageFact
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.run_records import RunRepositoryRecord
from orchestrator.domain.entities.step_run import StepRun

if TYPE_CHECKING:
    from orchestrator.application.analysis.signals import RepositorySignals


@dataclass(frozen=True)
class AttemptInputs:
    """One attempt with its row, its role, its reads (newest first) and its chosen facts."""

    attempt: Attempt
    row: StepRun
    role: str
    reads: Sequence[StoredRead] = ()
    fact_set: FactSet | None = None
    facts: AttemptFacts | None = None
    #: The harness money rows the budget gate counts for this attempt
    #: (`spend_figures.first_fact_money`), which need not come from the chosen fact set.
    fact_money: tuple[UsageFact, ...] = ()


@dataclass(frozen=True)
class RunInputs:
    run: Run
    rows: Sequence[StepRun]
    attempts: Sequence[AttemptInputs]
    records: Sequence[GateRecord]
    now: datetime
    run_repositories: Sequence[RunRepositoryRecord] = field(default_factory=tuple)
    #: Filled by the calculation (story 4); empty while a Run is live.
    code: Sequence[RepositorySignals] = field(default_factory=tuple)


def choose_fact_set(sets: Sequence[FactSet]) -> FactSet | None:
    """The newest fact set by `read_at` whose status is `ok` or `partial`, else `None`."""
    usable = [s for s in sets if s.status in ("ok", "partial")]
    return max(usable, key=lambda s: s.read_at, default=None)


def gateway_usd(attempt: AttemptInputs) -> Decimal | None:
    """The newest settled read's figure; `None` while no read is settled."""
    return next((read.usd for read, _ in attempt.reads if not read.provisional), None)


def harness_rows(attempt: AttemptInputs) -> tuple[UsageFact, ...]:
    """Harness money rows of the newest read that has any, else the gate's fact-set rows."""
    from_reads = next((rows for _, usage in attempt.reads if (rows := harness_money(usage))), ())
    if from_reads:
        return from_reads
    return attempt.fact_money or harness_money(attempt.facts.usage if attempt.facts else ())


def harness_usd(attempt: AttemptInputs) -> Decimal | None:
    rows = harness_rows(attempt)
    if not rows:
        return None
    return sum((u.usd or Decimal(0) for u in rows), Decimal(0))
