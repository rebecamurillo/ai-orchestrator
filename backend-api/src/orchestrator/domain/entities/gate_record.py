"""The gate record: one append-only line per Run transition, in the order they happened.

Every Run transition appends one (AD-8), and nothing ever updates or deletes one — the
repository port has `add` and `list_for_run` and no third method, which is how the rule is
kept rather than remembered. It is what the Operator reads to answer "why did this stop",
so `text` is a sentence and `event` is a token: the token is what the UI groups by, the
sentence is what a person reads.

`event` spans the three alphabets AD-8 names — a `ParkKind` for a machine stop, a
`SignalKind` for an operator action, and `start | done | failed | cancelled` for the Run's
own beginning and ends — plus the two bounded re-executions AD-9 records without any Run
transition (`redispatch`, `retry_auto`), which together are `GateEvent`. `actor` says which
of them: `machine` for a park or a redispatch the walker wrote, `operator` for a signal,
`terminal` for the resume path where a person drove the harness directly.

`path` is the row the record is about, `None` for a record about the Run itself; `payload`
carries whatever the event needs kept — the files a `continue` accepted, the budget a
`budget_raise` set.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.domain.statuses import Actor, GateEvent


class GateRecord(BaseModel):
    """One line of a Run's gate record, as it is stored."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    run_id: UUID
    at: datetime
    #: The `step_run.path` this record is about, or `None` when it is about the Run.
    path: str | None = None
    event: GateEvent
    actor: Actor
    text: str = ""
    #: The `attempt.n` the record belongs to, where it belongs to one.
    attempt_n: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
