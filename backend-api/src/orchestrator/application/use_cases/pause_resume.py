"""Reading a resume off the gate records: did this signal lift a pause (AD-13)?

Kept apart from `pause_stop.py` because `walk_context.py` reads it and `pause_stop.py` reads
`walk_context.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import takewhile

from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.statuses import PARK_KINDS


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
