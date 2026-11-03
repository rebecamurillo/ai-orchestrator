"""The stop a `pause` signal lands as (AD-13, 2026-11-01 amendment).

`signal_run` only records the request. The park is an execution write, so it is made by
`apply_step_result` through `park_before_next` at the moment it queues a successor: the row
that was executing has ended, nothing is killed, and the Run waits on the row that will run
next. That row is already `queued`, so `continue` writes no row and the walker finds it.
"""

from __future__ import annotations

from orchestrator.application.use_cases.walk_context import redispatches_to
from orchestrator.application.use_cases.writers import FINISHED, WriterPorts, park_run, queue_row
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.values import Park

#: What the Operator reads at the stop: where the Run will carry on.
PAUSED_REASON = "paused at the Operator's request; next: {path}"


def park_paused(ports: WriterPorts, run: Run, path: str) -> Run:
    """Park the Run `paused` on the row it will run next, clearing the request."""
    return park_run(
        ports, run, Park(kind="paused", reason=PAUSED_REASON.format(path=path), path=path)
    )


def park_before_next(ports: WriterPorts, run: Run, successor: StepRun) -> Run:
    """Park on the row the walker will run next, which is not always `successor`.

    After a redispatch the row that just finished is the target, and the rows between it and
    the verify row that failed are `done`. The walker's next row is that verify row
    (`walk._sent_back`), so it is queued here and named, rather than a row that will not run.
    """
    rows = ports.steps.list_for_run(run.id)
    next_up = next((row for row in rows if row.status == "queued"), None)
    if next_up is None:
        done = [row.seq for row in rows if row.status in FINISHED]
        sender = next(
            (
                row
                for row in rows
                if row.status == "error" and any(redispatches_to(row, seq) for seq in done)
            ),
            None,
        )
        next_up = queue_row(ports, sender) if sender is not None else successor
    return park_paused(ports, run, next_up.path)
