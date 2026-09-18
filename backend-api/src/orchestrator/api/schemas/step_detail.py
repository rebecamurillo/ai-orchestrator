"""Response schemas for the step-run detail endpoint (story 1-2)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AttemptDetailOut(BaseModel):
    """One attempt's full detail, as returned by the step-run detail endpoint.

    `dispatch_prompt` and `command` derive from the step's `with_resolved`: they are the
    same for every attempt of the step and carried here so the frontend needs only this
    object.  `result` is extracted per-attempt from the spec file at `end_sha`.
    """

    id: UUID
    n: int
    status: str
    token: str
    started_at: datetime | None
    ended_at: datetime | None
    seconds: float | None
    harness: str | None
    model: str | None
    session_id: str | None
    exit_code: int | None
    cost_usd: Decimal | None
    cost_provisional: bool
    tokens_in: int | None
    tokens_out: int | None
    #: The full dispatch sentence, or `None` for shell steps.
    dispatch_prompt: str | None
    #: The retry prompt declared in the Template, or `None` when absent.
    retry_prompt: str | None
    #: The `## Auto Run Result` section extracted from the spec file, or `None`.
    result: str | None
    #: `with_resolved['run']` for shell steps, else `None`.
    command: str | None


class StepDetailOut(BaseModel):
    """One step's full detail, as returned by the step-run detail endpoint.

    `attempts` is newest first (highest `n` first), consistent with every other endpoint
    that sorts attempts for display.
    """

    seq: int
    path: str
    label: str
    kind: str
    gate: str
    status: str
    token: str
    reason: str | None
    with_resolved: dict[str, Any]
    attempts: list[AttemptDetailOut]
