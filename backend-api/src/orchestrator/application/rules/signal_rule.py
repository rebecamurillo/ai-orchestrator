"""The `Rule` a signal's table row is, and the Run status a signal is admitted in by default."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import Actor, ParkKind, RunEvent, RunStatus, StepStatus
from orchestrator.domain.values import Signal

#: The `Run.status` values a signal that is not `cancel` is sent to.
PARKED: frozenset[RunStatus] = frozenset({"needs_you"})


@dataclass(frozen=True)
class Rule:
    """When one `Signal.kind` is admitted, and what its gate record says."""

    #: The park kinds this signal is admitted on, read only while the Run is `needs_you`.
    park_kinds: frozenset[ParkKind]
    #: The Run statuses it is admitted in.
    run_statuses: frozenset[RunStatus] = PARKED
    #: The parked row's `kind`, or `None` when any kind is admitted.
    row_kinds: frozenset[str] | None = None
    #: The parked row's `status`, or `None` when any status is admitted.
    row_statuses: frozenset[StepStatus] | None = None
    #: What the table states in words rather than in columns; `None` when it states nothing.
    #: Called with the Run, the parked row, the signal, and every row of the Run.
    extra: Callable[[Run, StepRun | None, Signal, Sequence[StepRun]], bool] | None = None
    #: The refusal `extra` alone earns, where the table has a better sentence than `INVALID`.
    #: Formatted with the Run, so a `budget_raise` can name the spend it has to beat.
    extra_refusal: str | None = None
    #: The Run transition this signal applies, or `None` when the Run's status is unchanged.
    run_event: RunEvent | None = None
    #: Who the gate record names.
    actor: Actor = "operator"
    #: The sentence the gate record carries when the payload supplies none.
    text: str = ""
    #: The payload key whose value is the gate record's text instead of `text`.
    text_key: str | None = None
    #: The gate record's text, built from the payload — for a sentence that has to quote a
    #: *validated* value, which is what `text_key` (the payload's own string, verbatim)
    #: cannot do. `None` from the builder falls through to `text`.
    text_from: Callable[[dict[str, Any]], str | None] | None = None
    #: True for the actions a person takes on the Run detail — what `admitted_signals`
    #: answers with. The terminal kinds are driven by the browser and the poll job.
    operator_action: bool = True
