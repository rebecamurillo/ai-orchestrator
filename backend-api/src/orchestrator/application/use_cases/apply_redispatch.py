"""AD-9's bounded route back, as `apply_step_result` applies it: a failed `verify` row sends
the Run to an earlier row, or says why it cannot.

Two bounds: a target that was skipped cannot be re-run, and a target whose
`redispatch_count` reached the Template's `max` parks `verify_failed` instead, unless the
verify row declares a consult (`verify_consult.py`, story 1-6): then the target is queued for
the senior and the stop parks only if the next failure finds the bound still used up. Under
the bound, the target is queued through AD-8's `redispatch` pair, counted, and recorded.
"""

from __future__ import annotations

from orchestrator.application.rules.signals import REBASELINE_FAILED
from orchestrator.application.use_cases import verify_consult
from orchestrator.application.use_cases.writers import (
    Entry,
    WriterPorts,
    record,
    require_row,
    set_row,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import step_transition
from orchestrator.domain.values import Park, Redispatch

#: The park a redispatch turns into once the Template's bound is used up (AD-9).
VERIFY_FAILED = "verify failed {n}/{n}"

#: What the gate record says when a redispatch fires.
REDISPATCHED = "verify failed, story re-dispatched {n}/{max}"


def redispatch(
    ports: WriterPorts,
    run: Run,
    row: StepRun,
    redispatch: Redispatch,
    attempt: Attempt | None,
) -> tuple[Park | None, bool]:
    """Send the Run back to an earlier row, or say why it cannot (AD-9's two bounds)."""
    target = require_row(ports, run.id, redispatch.target_seq)
    if target.status == "skipped":
        return Park(kind="verify_failed", reason=REBASELINE_FAILED, path=row.path), False
    if target.redispatch_count >= redispatch.max:
        reason = VERIFY_FAILED.format(n=target.redispatch_count + 1)
        exhausted = Park(kind="verify_failed", reason=reason, path=row.path)
        return verify_consult.offer(ports, run, row, target, exhausted)
    count = target.redispatch_count + 1
    set_row(
        ports,
        target,
        status=step_transition(target.status, "redispatch"),
        redispatch_count=count,
    )
    record(
        ports,
        run,
        Entry(
            event="redispatch",
            actor="machine",
            path=row.path,
            text=REDISPATCHED.format(n=count, max=redispatch.max),
            attempt_n=attempt.n if attempt is not None else None,
        ),
    )
    return None, True
