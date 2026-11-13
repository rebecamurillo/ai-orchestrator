"""Which story frames the plan holds and which of them are done."""

from __future__ import annotations

from orchestrator.application.metrics.inputs import RunInputs
from orchestrator.application.rules.frames import story_frame
from orchestrator.domain.entities.step_run import StepRun


def story_rows(inputs: RunInputs) -> dict[str, list[StepRun]]:
    frames: dict[str, list[StepRun]] = {}
    for row in sorted(inputs.rows, key=lambda r: r.seq):
        if (frame := story_frame(row.path)) is not None:
            frames.setdefault(frame, []).append(row)
    return frames


def stories_done(inputs: RunInputs) -> tuple[int, int]:
    """(stories with every row done or skipped and one done, stories the plan holds)."""
    frames = story_rows(inputs)
    done = sum(
        1
        for rows in frames.values()
        if all(r.status in ("done", "skipped") for r in rows)
        and any(r.status == "done" for r in rows)
    )
    return done, len(frames)
