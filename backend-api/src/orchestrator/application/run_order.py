"""The order of a Run's steps around each agent, read off the plan (AD-40 "The order").

Also home of `STEP_TOKENS`, so `run_graph` can import `build_run_order` without a cycle;
`application.graph` re-exports it.
"""

from __future__ import annotations

from collections.abc import Sequence

from orchestrator.application.graph_schema import RunOrderFrame, RunOrderPhase, RunOrderRow
from orchestrator.application.rules.frames import (
    epic_frame,
    rows_in_frame,
    story_frame,
)
from orchestrator.application.steps import AGENT_KIND
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import StepStatus

#: Step tokens (Consistency Conventions — Status tokens), for a run graph's per-row nodes.
STEP_TOKENS: dict[StepStatus, str] = {
    "planned": "QUE",
    "queued": "QUE",
    "running": "RUN",
    "done": "DON",
    "blocked": "BLK",
    "checkpoint": "CHK",
    "error": "ERR",
    "skipped": "SKP",
}

ROOT_FRAME = "root"


def _frames(rows: Sequence[StepRun]) -> list[str]:
    """`root`, then every epic and story frame in plan order, an epic before its first story."""
    frames = [ROOT_FRAME]
    for row in rows:
        for frame in (epic_frame(row.path), story_frame(row.path)):
            if frame is not None and frame not in frames:
                frames.append(frame)
    return frames


def _members(rows: Sequence[StepRun], frame: str) -> tuple[list[StepRun], list[StepRun]]:
    """The frame's own rows and the rows of the frames nested in it, each in `seq` order."""
    if frame == ROOT_FRAME:
        within = list(rows)
        own = [r for r in within if epic_frame(r.path) is None and story_frame(r.path) is None]
    else:
        within = rows_in_frame(rows, frame)
        own = [r for r in within if story_frame(r.path) in (None, frame)]
    nested = [r for r in within if r not in own]
    return own, nested


def _phase(row: StepRun, boundary: int, *, own_agent: bool) -> RunOrderPhase:
    if own_agent and row.kind == AGENT_KIND:
        return "AGENT"
    return "BEFORE" if row.seq < boundary else "AFTER"


def _entry(rows: Sequence[StepRun], frame: str) -> RunOrderFrame | None:
    own, nested = _members(rows, frame)
    own_agents = [r.seq for r in own if r.kind == AGENT_KIND]
    if own_agents:
        boundary = min(own_agents)
    elif any(r.kind == AGENT_KIND for r in nested):
        boundary = min(r.seq for r in nested)
    else:
        return None
    if not own:
        return None
    return RunOrderFrame(
        frame=frame,
        rows=tuple(
            RunOrderRow(
                seq=r.seq,
                path=r.path,
                label=r.label,
                kind=r.kind,
                token=STEP_TOKENS[r.status],
                phase=_phase(r, boundary, own_agent=bool(own_agents)),
            )
            for r in own
        ),
    )


def build_run_order(rows: Sequence[StepRun]) -> tuple[RunOrderFrame, ...]:
    """One entry per frame holding an agent row at any depth and at least one own row."""
    ordered = sorted(rows, key=lambda row: row.seq)
    entries = (_entry(ordered, frame) for frame in _frames(ordered))
    return tuple(entry for entry in entries if entry is not None)
