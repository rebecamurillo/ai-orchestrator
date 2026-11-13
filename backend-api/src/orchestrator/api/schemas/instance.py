"""The HTTP shape of `GET /instance/activity` (SPEC CAP-3, AD-30).

Every field is required, nullable where the use case's is, so the generated TypeScript type
has no optional keys.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from orchestrator.api.schemas.common import StorableText, UtcTimestamp
from orchestrator.application.use_cases.instance_activity import (
    EngineRun,
    HoldView,
    InstanceActivity,
    WorkingStep,
)
from orchestrator.domain.statuses import ParkKind, RunStatus


class WorkingStepOut(BaseModel):
    run_id: UUID
    run_label: str
    path: str
    kind: str
    started_at: UtcTimestamp | None

    @classmethod
    def of(cls, step: WorkingStep) -> WorkingStepOut:
        return cls(
            run_id=step.run_id,
            run_label=step.run_label,
            path=step.path,
            kind=step.kind,
            started_at=step.started_at,
        )


class EngineRunOut(BaseModel):
    run_id: UUID
    run_label: str
    status: RunStatus
    park_kind: ParkKind | None
    queue_reason: str | None

    @classmethod
    def of(cls, run: EngineRun) -> EngineRunOut:
        return cls(
            run_id=run.run_id,
            run_label=run.run_label,
            status=run.status,
            park_kind=run.park_kind,
            queue_reason=run.queue_reason,
        )


class HoldOut(BaseModel):
    held_at: UtcTimestamp
    expires_at: UtcTimestamp
    reason: str

    @classmethod
    def of(cls, hold: HoldView) -> HoldOut:
        return cls(held_at=hold.held_at, expires_at=hold.expires_at, reason=hold.reason)


class HoldIn(BaseModel):
    ttl_seconds: int = Field(ge=1, le=3600)
    reason: StorableText = Field(max_length=200)


class HoldConflictOut(BaseModel):
    """The 409 body: a problem document whose `errors` are the working steps."""

    type: str
    title: str
    status: int
    detail: str
    errors: list[WorkingStepOut]


class InstanceActivityOut(BaseModel):
    working: list[WorkingStepOut]
    in_engine: list[EngineRunOut]
    hold: HoldOut | None
    dbos_application_version: str

    @classmethod
    def of(cls, activity: InstanceActivity) -> InstanceActivityOut:
        return cls(
            working=[WorkingStepOut.of(step) for step in activity.working],
            in_engine=[EngineRunOut.of(run) for run in activity.in_engine],
            hold=None if activity.hold is None else HoldOut.of(activity.hold),
            dbos_application_version=activity.dbos_application_version,
        )
