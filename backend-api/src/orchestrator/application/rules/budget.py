"""`check`: whether a Run has spent past its budget (AD-11's own park kind).

One rule, read off `Run.spend_usd`/`Run.budget_usd` alone: no repository, no Gateway call —
`spend_usd` is already the sum `application/use_cases/spend.py::record_attempt_spend` wrote.
`domain/values.py::Park` and `"budget"` (`domain/statuses.py::ParkKind`) already exist; this
module builds the value, it invents nothing.

Nothing here calls this. No call site wires a budget-park routing, a re-check schedule, or a
raised-budget resume — those are 5.7's and Epic 6's own scope (this story's own Boundaries).
"""

from __future__ import annotations

from orchestrator.domain.entities.run import Run
from orchestrator.domain.values import Park


def check(run: Run) -> Park | None:
    """`Park(kind="budget", ...)` once spend exceeds budget; `None` at or under it."""
    if run.spend_usd <= run.budget_usd:
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
    reason = f"budget ${run.spend_usd:.2f} / ${run.budget_usd:.2f}"
    return Park(kind="budget", reason=reason)
