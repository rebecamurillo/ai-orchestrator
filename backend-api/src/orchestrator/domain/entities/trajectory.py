"""The Trajectory: one append-only row per Story that reaches `done` (SPEC CAP-9, AD-19).

Written once, by `application/use_cases/record_trajectory.py`, the moment a Story frame's
`build` row is `done` and its `verify` row is `done | skipped` — never updated, never
deleted (`domain/ports/trajectories.py` exposes `add` and `list_for_project` only). It is
what SM-1 ("was this Story unattended") and SM-3 (cost and wall-clock per harness) are
computed from, and what a future fine-tuning set reads its trajectories out of (Epic 7).

`attempts` is the `build` row's own attempts, in order — the only row kind AD-14 wires
`start_sha`/`end_sha`/the usage columns onto — and `route` on each one is the `StepStatus`
that attempt's row reached through it (`domain/entities/attempt.py`'s own docstring):
`human_actions` empty and every `route == "done"` is SM-1's "unattended" (the brief's own
words). `human_actions` is every gate record about a row of this frame that is either a park
(a stop for a person) or an Operator's own signal — never the automatic bookkeeping AD-9
records without either (`redispatch`, `retry_auto`) and never a Run's own lifecycle line.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AttemptRecord(BaseModel):
    """One attempt at the frame's `build` row, as the trajectory keeps it."""

    model_config = ConfigDict(frozen=True)

    n: int
    started_at: datetime | None = None
    ended_at: datetime | None = None
    exit_code: int | None = None
    session_id: str | None = None
    cost_usd: Decimal | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    #: The `StepStatus` this attempt's row reached through it — `"done"` for every attempt
    #: of an unattended Story (SM-1).
    route: str


class ProtectedPathHit(BaseModel):
    """One path AD-17 caught inside this frame, and how it changed."""

    model_config = ConfigDict(frozen=True)

    path: str
    kind: str


class ProtectedPathsResult(BaseModel):
    """AD-17 over this frame: what it caught, and what the Operator accepted."""

    model_config = ConfigDict(frozen=True)

    hits: tuple[ProtectedPathHit, ...] = ()
    accepted: tuple[str, ...] = ()


class GateResults(BaseModel):
    """What each of the frame's three gated rows reported, read off the rows themselves."""

    model_config = ConfigDict(frozen=True)

    #: The `build` row's own gate — always `"liveness"` (NFR-2: a Story step is never green).
    build: str
    #: The `verify` row's final status: `"done"` or `"skipped"`.
    verify: str
    #: The `commit-guard` row's own outcome: `"done"` or `"no changes"`.
    commit_guard: str
    protected_paths: ProtectedPathsResult = ProtectedPathsResult()


class HumanAction(BaseModel):
    """One gate record of this frame that was a stop for a person, or a person's own signal."""

    model_config = ConfigDict(frozen=True)

    event: str
    at: datetime


class Trajectory(BaseModel):
    """One Story's trajectory, as it is stored. Unique on `(run_id, frame)`."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    run_id: UUID
    project_id: UUID
    repository_id: UUID
    story_id: str | None = None
    #: The `epics[n]` index this frame is nested under, or `0` for a Run with no epic loop.
    epic_index: int
    #: The innermost `…stories[n]` prefix of the frame's rows (`StepRun.frame`).
    frame: str
    harness: str | None = None
    model: str | None = None
    attempts: tuple[AttemptRecord, ...] = ()
    gate_results: GateResults
    cost_usd: Decimal = Decimal("0")
    tokens_in: int = 0
    tokens_out: int = 0
    wall_clock_seconds: float = 0.0
    #: The story file's committed text at `end_sha`.
    story_file: str = ""
    #: The frame's first attempt's own `start_sha` (AD-17's rule, reused).
    start_sha: str | None = None
    #: `HEAD` after the commit-guard committed (or found nothing to commit).
    end_sha: str | None = None
    human_actions: tuple[HumanAction, ...] = Field(default_factory=tuple)
    recorded_at: datetime
