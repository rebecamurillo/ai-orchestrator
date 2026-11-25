"""`GateRecordOut` and `SummaryOut`, moved out of `schemas/run_views.py` on line count and
imported back there so every existing import keeps resolving."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from orchestrator.api.schemas.board_view import ProgressOut
from orchestrator.api.schemas.common import UtcTimestamp
from orchestrator.api.schemas.common import drop_default as _drop_default
from orchestrator.application.use_cases.run_view_types import Summary
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.statuses import Actor, GateEvent


class GateRecordOut(BaseModel):
    id: UUID
    at: UtcTimestamp
    path: str | None
    event: GateEvent
    actor: Actor
    text: str
    attempt_n: int | None
    #: The delivery mode the operator chose for an Answer or Retry signal (`"session"` or
    #: `"restart"`), or `null` for a legacy record whose payload predates story 3-4 or for
    #: records that carry no mode (e.g. `start`, `plan_stale`). `_drop_default`-guarded so
    #: every web-client test fixture that predates this field keeps compiling without it.
    mode: str | None = Field(default=None, json_schema_extra=_drop_default)

    @classmethod
    def of(cls, record: GateRecord) -> GateRecordOut:
        return cls(
            id=record.id,
            at=record.at,
            path=record.path,
            event=record.event,
            actor=record.actor,
            text=record.text,
            attempt_n=record.attempt_n,
            mode=record.payload.get("mode") or None,
        )


class SummaryOut(BaseModel):
    progress: ProgressOut | None
    links: list[str]
    skipped: list[str]
    #: The epic numbers `skip_epic` gave up the push on (6.5). `_drop_default`-guarded like
    #: `cost_provisional`/`row_kind` above: an existing web-client test fixture predates this
    #: field and must keep compiling without it.
    skipped_epics: list[int] = Field(default_factory=list, json_schema_extra=_drop_default)

    @classmethod
    def of(cls, summary: Summary) -> SummaryOut:
        return cls(
            progress=None if summary.progress is None else ProgressOut.of(summary.progress),
            links=list(summary.links),
            skipped=list(summary.skipped),
            skipped_epics=list(summary.skipped_epics),
        )
