"""One execution of one row: the `n`th attempt, and everything it is known to have done.

`n` is 1-based per row and unique with `step_run_id`, so "attempt 2 of `steps[3]`" names one
record whatever else is running. An attempt is written in **two halves** (AD-8), and every
optional field below belongs to one of them: `AttemptRepository.mark_started` records
`started_at`, `start_sha`, `frozen_test_files` and `pgid` in its own unit of work *before*
the harness is awaited, and `mark_finished` records `ended_at`, `end_sha`, `exit_code`,
`session_id`, the usage and `log_path` right after it exits. A backend restart between the
two finds the start half stored, which is what lets FR-12 report an interrupted attempt
instead of losing it.

`status` is a `StepStatus` — the status the row reached *through this attempt*: `running`
while in flight, then one of `done | blocked | checkpoint | error | skipped`. A second
alphabet here would only give 4.5 two vocabularies to reconcile.

The last eight fields are the agent extras (AD-10, AD-11): only an `agent` row's attempt
fills them, and `cost_usd` is `None` until the gateway answers — `cost_provisional` says
the number is the harness's own estimate rather than LiteLLM's settled spend.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.domain.statuses import StepStatus


class Attempt(BaseModel):
    """One attempt at one row, as it is stored."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    run_id: UUID
    step_run_id: UUID
    #: 1-based within the row, unique with `step_run_id`.
    n: int
    status: StepStatus
    started_at: datetime | None = None
    ended_at: datetime | None = None
    #: Opaque JSON the durable-engine adapter owns (AD-6).
    engine_ref: dict[str, Any] = Field(default_factory=dict)
    #: HEAD after the WIP and prepare commits — the start of this attempt's agent range.
    start_sha: str | None = None
    #: HEAD when the harness exited — the end of it (AD-9).
    end_sha: str | None = None
    #: The protected test files as they stood at the story frame's first attempt; `None` on
    #: every attempt that is not that one.
    frozen_test_files: tuple[str, ...] | None = None
    log_path: str | None = None
    exit_code: int | None = None
    #: The log path or a short output, whichever the kind produced.
    output_ref: str | None = None
    harness: str | None = None
    model: str | None = None
    #: The harness's own session id, used only to resume this same row (AD-10).
    session_id: str | None = None
    #: The process group the harness ran in, recorded before it is awaited (AD-14).
    pgid: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: Decimal | None = None
    #: True while `cost_usd` is the harness's estimate and not the gateway's settled spend.
    cost_provisional: bool = False
