"""`check`: whether a Run has spent past its budget (AD-11's own park kind).

One rule, read off `Run.gate_spend_usd`/`Run.budget_usd` alone: no repository, no Gateway
call — `gate_spend_usd` is the higher of the gateway and harness totals
`application/use_cases/spend.py::record_attempt_spend` recomputed (RM-4).
`domain/values.py::Park` and `"budget"` (`domain/statuses.py::ParkKind`) already exist; this
module builds the value, it invents nothing.

Nothing here calls this. No call site wires a budget-park routing, a re-check schedule, or a
raised-budget resume — those are 5.7's and Epic 6's own scope (this story's own Boundaries).
"""

from __future__ import annotations

from decimal import Decimal

from orchestrator.domain.entities.run import Run
from orchestrator.domain.values import Park


def figure(run: Run) -> Decimal:
    """The spend every budget comparison uses: the higher of the gateway and harness totals."""
    return run.gate_spend_usd


def check(run: Run) -> Park | None:
    """`Park(kind="budget", ...)` once spend exceeds budget; `None` at or under it.

    When `run.budget_usd` is `None` the run is uncapped: spend tracking continues but no
    park ever fires (story 3-2, AC2).
    """
    if run.budget_usd is None:
        return None
    if figure(run) <= run.budget_usd:
        return None
    return forced(run)


def forced(run: Run) -> Park:
    """`Park(kind="budget", ...)` unconditionally — for the harness's own cap exit (AD-10,
    FR-14): `--max-budget-usd` already stopped the process, so the figures are read and
    reported regardless of what the comparison in `check` would say on its own.

    The reason is always rendered to two decimal places (`:.2f`) regardless of how many
    `Attempt.cost_usd` summed into `run.spend_usd`: a real Gateway figure round-trips a
    float's own precision (`infrastructure/gateway/litellm_spend.py::_decimal`), and a
    park reason is a sentence an operator reads, not the wire `MoneyStr` (which keeps all
    six of the column's own decimal places, `api/schemas/common.py::_money_string`).
    """
    if run.budget_usd is None:
        # Defensive: `--max-budget-usd` was absent so Claude cannot self-cap; the harness
        # exited for another reason. Report spend only (story 3-2, "Block If" invariant).
        reason = f"budget ${figure(run):.2f} / (no cap)"
    else:
        reason = f"budget ${figure(run):.2f} / ${run.budget_usd:.2f}"
    return Park(kind="budget", reason=reason)
