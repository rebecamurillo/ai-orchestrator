"""The facts one attempt left behind, stored once when it ends (SPEC CAP-2).

A `FactSet` is the header of one extraction of one attempt's log; the row entities below it
carry no ids or parent ids, because the repository assigns them on save. `AttemptFacts` is
what an extractor returns, unsaved. Nothing here is ever updated or deleted.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

FactSetStatus = Literal["ok", "partial", "failed"]
UsageSource = Literal["harness", "gateway"]
UsageClass = Literal[
    "money",
    "input_uncached",
    "cache_read",
    "cache_write_5m",
    "cache_write_1h",
    "cache_write_unsplit",
    "output",
    "thinking",
    "gateway_prompt",
    "gateway_completion",
]
GatewayTrigger = Literal["attempt_end", "run_end", "recalculation"]
EventKind = Literal["write", "test_run"]


class FactSet(BaseModel):
    """One extraction of one attempt's log, unique per attempt, extractor and version."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    attempt_id: UUID
    run_id: UUID
    extractor: str
    extractor_version: int
    read_at: datetime
    status: FactSetStatus
    reason: str | None = None
    subscription: bool | None = None


class GatewayRead(BaseModel):
    """One read of the gateway's spend for an attempt."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    attempt_id: UUID
    run_id: UUID
    read_at: datetime
    trigger: GatewayTrigger
    rows: int | None = None
    calls: int | None = None
    provisional: bool
    capped: bool = False
    usd: Decimal
    prompt: int | None = None
    completion: int | None = None


class UsageFact(BaseModel):
    """Usage of one class, by one source, for one model and conversation."""

    model_config = ConfigDict(frozen=True)

    source: UsageSource
    model: str | None = None
    conversation: str | None = None
    subagent_type: str | None = None
    usage_class: UsageClass
    tokens: int | None = None
    usd: Decimal | None = None
    calls: int | None = None


class RequestFact(BaseModel):
    """One model request's token classes."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    model: str
    conversation: str
    at: datetime | None = None
    input_uncached: int
    cache_read: int
    cache_write_5m: int
    cache_write_1h: int
    output: int


class ActivityFact(BaseModel):
    """What one conversation did with one tool."""

    model_config = ConfigDict(frozen=True)

    conversation: str
    tool: str
    calls: int
    errors: int
    files_read: int
    files_edited: int
    test_runs: int
    messages: int


class GapFact(BaseModel):
    """The spacing of one conversation's messages, in seconds."""

    model_config = ConfigDict(frozen=True)

    conversation: str
    messages: int
    first_at: datetime
    last_at: datetime
    gaps_s: tuple[int, ...]


class EventFact(BaseModel):
    """One write or test run an attempt performed."""

    model_config = ConfigDict(frozen=True)

    at: datetime
    conversation: str
    kind: EventKind
    path: str | None = None
    command: str | None = None
    exit_code: int | None = None


class AttemptFacts(BaseModel):
    """What an extractor returns for one attempt: unsaved rows and how complete they are."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "partial"] = "ok"
    reason: str | None = None
    usage: tuple[UsageFact, ...] = ()
    requests: tuple[RequestFact, ...] = ()
    activity: tuple[ActivityFact, ...] = ()
    gaps: tuple[GapFact, ...] = ()
    events: tuple[EventFact, ...] = ()
