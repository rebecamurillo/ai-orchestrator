"""The HTTP shape of one `GET /projects/{id}/trajectories.jsonl` line (SPEC CAP-6, AD-19,
FR-32 export).

One `TrajectoryLineOut` per line, newest first — no `{items, next_cursor}` envelope, because
the response is `application/x-ndjson`, not one JSON document (`api/routers/trajectories.py`).
Every `Trajectory` field is rendered, `story_file` included (the binding rule's own words),
through the same `MoneyStr` / `UtcTimestamp` conventions `HistoryRowOut` uses: a JSON number
would lose a fraction-of-a-cent model cost, and a naive timestamp would be ambiguous about
its zone — exactly the comparison SM-1 and SM-3 exist to make readable.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from orchestrator.api.schemas.common import MoneyStr, UtcTimestamp
from orchestrator.domain.entities.trajectory import (
    AttemptRecord,
    GateResults,
    HumanAction,
    ProtectedPathHit,
    ProtectedPathsResult,
    Trajectory,
)


class AttemptRecordOut(BaseModel):
    """One attempt at the frame's `build` row, as this line prints it."""

    n: int
    started_at: UtcTimestamp | None
    ended_at: UtcTimestamp | None
    exit_code: int | None
    session_id: str | None
    cost_usd: MoneyStr | None
    tokens_in: int | None
    tokens_out: int | None
    route: str

    @classmethod
    def of(cls, attempt: AttemptRecord) -> AttemptRecordOut:
        return cls(
            n=attempt.n,
            started_at=attempt.started_at,
            ended_at=attempt.ended_at,
            exit_code=attempt.exit_code,
            session_id=attempt.session_id,
            cost_usd=attempt.cost_usd,
            tokens_in=attempt.tokens_in,
            tokens_out=attempt.tokens_out,
            route=attempt.route,
        )


class ProtectedPathHitOut(BaseModel):
    """One path AD-17 caught inside this frame, and how it changed."""

    path: str
    kind: str

    @classmethod
    def of(cls, hit: ProtectedPathHit) -> ProtectedPathHitOut:
        return cls(path=hit.path, kind=hit.kind)


class ProtectedPathsResultOut(BaseModel):
    """AD-17 over this frame: what it caught, and what the Operator accepted."""

    hits: list[ProtectedPathHitOut]
    accepted: list[str]

    @classmethod
    def of(cls, result: ProtectedPathsResult) -> ProtectedPathsResultOut:
        return cls(
            hits=[ProtectedPathHitOut.of(hit) for hit in result.hits],
            accepted=list(result.accepted),
        )


class GateResultsOut(BaseModel):
    """What each of the frame's three gated rows reported."""

    build: str
    verify: str
    commit_guard: str
    protected_paths: ProtectedPathsResultOut

    @classmethod
    def of(cls, gate_results: GateResults) -> GateResultsOut:
        return cls(
            build=gate_results.build,
            verify=gate_results.verify,
            commit_guard=gate_results.commit_guard,
            protected_paths=ProtectedPathsResultOut.of(gate_results.protected_paths),
        )


class HumanActionOut(BaseModel):
    """One gate record of this frame that was a stop for a person, or a person's own signal."""

    event: str
    at: UtcTimestamp

    @classmethod
    def of(cls, action: HumanAction) -> HumanActionOut:
        return cls(event=action.event, at=action.at)


class TrajectoryLineOut(BaseModel):
    """One `trajectories.jsonl` line: one Story's whole trajectory (5.9), as stored."""

    id: UUID
    run_id: UUID
    project_id: UUID
    repository_id: UUID
    story_id: str | None
    epic_index: int
    frame: str
    harness: str | None
    model: str | None
    attempts: list[AttemptRecordOut]
    gate_results: GateResultsOut
    cost_usd: MoneyStr
    tokens_in: int
    tokens_out: int
    wall_clock_seconds: float
    story_file: str
    start_sha: str | None
    end_sha: str | None
    human_actions: list[HumanActionOut]
    recorded_at: UtcTimestamp

    @classmethod
    def of(cls, trajectory: Trajectory) -> TrajectoryLineOut:
        return cls(
            id=trajectory.id,
            run_id=trajectory.run_id,
            project_id=trajectory.project_id,
            repository_id=trajectory.repository_id,
            story_id=trajectory.story_id,
            epic_index=trajectory.epic_index,
            frame=trajectory.frame,
            harness=trajectory.harness,
            model=trajectory.model,
            attempts=[AttemptRecordOut.of(attempt) for attempt in trajectory.attempts],
            gate_results=GateResultsOut.of(trajectory.gate_results),
            cost_usd=trajectory.cost_usd,
            tokens_in=trajectory.tokens_in,
            tokens_out=trajectory.tokens_out,
            wall_clock_seconds=trajectory.wall_clock_seconds,
            story_file=trajectory.story_file,
            start_sha=trajectory.start_sha,
            end_sha=trajectory.end_sha,
            human_actions=[HumanActionOut.of(action) for action in trajectory.human_actions],
            recorded_at=trajectory.recorded_at,
        )
