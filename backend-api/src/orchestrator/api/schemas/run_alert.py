"""The Alert's own HTTP shapes: the attribution eyebrow, the done-checkpoint summary, and
the Alert itself (SPEC CAP-10, CAP-15).

Split out of `api/schemas/run_views.py` on line count alone when 6.7 added `TerminalOut` to a
module already at 400 — the same seam `application/use_cases/run_views_alert.py` cut on the
builder side, for the same reason, so the two halves of "the alert" now sit in matching
modules on both sides of the API boundary. Every name here is imported straight back into
`run_views.py`, so no existing import moved.

`_drop_default` travels with them: several fields here are defaulted so that a web-client
fixture written before the field still compiles, and the JSON-schema `default` has to be
stripped for `openapi-typescript` to emit them as optional (AD-3).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from orchestrator.api.schemas.common import MoneyStr, UtcTimestamp
from orchestrator.application.use_cases.run_views import Alert, Attribution, CheckpointStory
from orchestrator.domain.statuses import ParkKind


def _drop_default(schema: dict[str, Any]) -> None:
    """Strip the JSON-schema `default` a defaulted field carries, so `openapi-typescript`
    (`defaultNonNullable`) still emits it as optional — `run_views.py` states the same rule
    for its own defaulted fields, and the two definitions are one line each rather than an
    import that would have to run the other way."""
    schema.pop("default", None)


class AttributionOut(BaseModel):
    """The blocked Question's eyebrow (5.10, SPEC CAP-10): `Agent · {harness} · {model} ·
    {ended_at}`."""

    harness: str | None
    model: str | None
    ended_at: UtcTimestamp | None

    @classmethod
    def of(cls, attribution: Attribution) -> AttributionOut:
        return cls(
            harness=attribution.harness, model=attribution.model, ended_at=attribution.ended_at
        )


class CheckpointStoryOut(BaseModel):
    """The done-checkpoint's own summary line (story 6-2): `story {id} · {title} ·
    {attempts} attempts · ${cost} · verify {done|skipped}`."""

    story_id: str
    title: str
    attempts: int
    cost_usd: MoneyStr
    verify: str

    @classmethod
    def of(cls, story: CheckpointStory) -> CheckpointStoryOut:
        return cls(
            story_id=story.story_id,
            title=story.title,
            attempts=story.attempts,
            cost_usd=str(story.cost_usd),
            verify=story.verify,
        )


class AlertOut(BaseModel):
    token: str
    reason: str | None
    park_kind: ParkKind | None
    #: `.of()` always sets the real value; see `_drop_default` — predates this field (5.10).
    attribution: AttributionOut | None = Field(default=None, json_schema_extra=_drop_default)
    #: `None` predates story 6-2. The parked row's own `kind`: a `checkpoint` park's
    #: `StopBody` case is `agent` (spec checkpoint) or anything else (done checkpoint).
    row_kind: str | None = Field(default=None, json_schema_extra=_drop_default)
    #: Set only for a done checkpoint. `None` predates story 6-2.
    checkpoint_story: CheckpointStoryOut | None = Field(
        default=None, json_schema_extra=_drop_default
    )
    #: The parking gate record's own payload (6.6) — AD-17's `{"hits": [{path, kind}]}` on a
    #: `protected_path` stop, `{}` on every other. `dict[str, Any]`, the type `GateRecord.
    #: payload` itself carries: a typed model here would fix a shape the record deliberately
    #: leaves open ("whatever the event needs kept", its own docstring).
    payload: dict[str, Any] = Field(default_factory=dict, json_schema_extra=_drop_default)

    @classmethod
    def of(cls, alert: Alert) -> AlertOut:
        attribution = None if alert.attribution is None else AttributionOut.of(alert.attribution)
        checkpoint_story = alert.checkpoint_story
        story = None if checkpoint_story is None else CheckpointStoryOut.of(checkpoint_story)
        return cls(
            token=alert.token,
            reason=alert.reason,
            park_kind=alert.park_kind,
            attribution=attribution,
            row_kind=alert.row_kind,
            checkpoint_story=story,
            payload=alert.payload,
        )
