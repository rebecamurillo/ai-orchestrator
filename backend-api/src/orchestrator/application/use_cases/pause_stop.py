"""The stop a `pause` signal lands as (AD-13, 2026-11-01 amendment).

`signal_run` only records the request. The park is an execution write, so it is made by
`apply_step_result` through `park_paused` at the moment it queues a successor: the row that
was executing has ended, nothing is killed, and the Run waits on the row that would have
run next. That row is already `queued`, so `continue` writes no row and the walker finds it.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import takewhile

from orchestrator.application.use_cases.writers import WriterPorts, park_run
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.statuses import PARK_KINDS
from orchestrator.domain.values import Park

#: What the Operator reads at the stop: where the Run will carry on.
PAUSED_REASON = "paused at the Operator's request; next: {path}"


def park_paused(ports: WriterPorts, run: Run, path: str) -> Run:
    """Park the Run `paused` on the row it will run next, clearing the request."""
    return park_run(
        ports, run, Park(kind="paused", reason=PAUSED_REASON.format(path=path), path=path)
    )


def resumed_a_pause(records: Sequence[GateRecord], resume: GateRecord) -> bool:
    """Whether `resume` answered a `paused` stop, read off the Run's own gate records.

    The stop a signal answers is the latest stop recorded before it. A `continue` that lifted
    a pause is not the `continue` that approves a spec checkpoint or a stale plan, and the row
    that runs next must not be told it is.
    """
    stops = [
        line.event
        for line in takewhile(lambda line: line.id != resume.id, records)
        if line.event in PARK_KINDS
    ]
    return bool(stops) and stops[-1] == "paused"
