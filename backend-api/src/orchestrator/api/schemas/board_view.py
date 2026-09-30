"""The Board's own wire shapes — `GET /runs?view=board` (SPEC CAP-12, CAP-14).

Split out of `api/schemas/run_views.py` on line count alone (`backend-api/AGENTS.md`'s
400-line module limit), to make room for 5.10's `AttributionOut`/`LatestAttemptOut.
cost_provisional` — the same reason `application/use_cases/run_view_types.py` split its own
module's dataclasses out. `run_views.py` imports every name back for re-export, so
`api/routers/run.py` and `tests/unit/test_run_view_schemas.py` (which import `BoardOut`/
`CardOut` from `run_views`) keep resolving through the one module both used to.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from orchestrator.api.schemas.common import UtcTimestamp
from orchestrator.application.use_cases.run_views import BoardView, Card, Progress
from orchestrator.domain.statuses import ParkKind, RunStatus


class ProgressOut(BaseModel):
    epics_done: int | None
    epics_total: int | None
    stories_done: int
    stories_total: int
    links: int

    @classmethod
    def of(cls, progress: Progress) -> ProgressOut:
        return cls(
            epics_done=progress.epics_done,
            epics_total=progress.epics_total,
            stories_done=progress.stories_done,
            stories_total=progress.stories_total,
            links=progress.links,
        )


class CardOut(BaseModel):
    id: UUID
    token: str
    status: RunStatus
    park_kind: ParkKind | None
    branch: str
    project_name: str
    repository_slug: str
    current_step_label: str
    harness: str | None
    template: str
    version: int
    progress: ProgressOut | None
    kind_label: str | None
    age_seconds: float
    needs_you_since: UtcTimestamp | None

    @classmethod
    def of(cls, card: Card) -> CardOut:
        return cls(
            id=card.id,
            token=card.token,
            status=card.status,
            park_kind=card.park_kind,
            branch=card.branch,
            project_name=card.project_name,
            repository_slug=card.repository_slug,
            current_step_label=card.current_step_label,
            harness=card.harness,
            template=card.template,
            version=card.version,
            progress=None if card.progress is None else ProgressOut.of(card.progress),
            kind_label=card.kind_label,
            age_seconds=card.age_seconds,
            needs_you_since=card.needs_you_since,
        )


class BoardColumnsOut(BaseModel):
    queued: list[CardOut]
    running: list[CardOut]
    needs_you: list[CardOut]
    done: list[CardOut]
    failed: list[CardOut]


class BoardCountsOut(BaseModel):
    running: int
    queued: int
    needs_you: int


class BoardOut(BaseModel):
    """`GET /runs?view=board`. Five columns, always present; `counts` sums three of them."""

    columns: BoardColumnsOut
    counts: BoardCountsOut
    generated_at: UtcTimestamp

    @classmethod
    def of(cls, view: BoardView) -> BoardOut:
        return cls(
            columns=BoardColumnsOut(
                queued=[CardOut.of(card) for card in view.columns.queued],
                running=[CardOut.of(card) for card in view.columns.running],
                needs_you=[CardOut.of(card) for card in view.columns.needs_you],
                done=[CardOut.of(card) for card in view.columns.done],
                failed=[CardOut.of(card) for card in view.columns.failed],
            ),
            counts=BoardCountsOut(
                running=view.counts.running,
                queued=view.counts.queued,
                needs_you=view.counts.needs_you,
            ),
            generated_at=view.generated_at,
        )
