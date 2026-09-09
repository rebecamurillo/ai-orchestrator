"""One Story frame as the walker reads it, and the two facts every row of it needs (AD-17).

Split out of `use_cases/walk.py`, which is at the 400-line cap `backend-api/AGENTS.md`
declares and `tests/unit/test_source_limits.py` enforces. The seam is the one the walk
already had: `walk.py` owns *what runs next and how a Run ends*, and this module owns *what
one row's Story frame says*, which is read once per row and handed over as frozen values.

Why any of it exists is unchanged from where it was written. A row a `verify` step sent back
needs facts about a *different* row (FR-10), AD-17's rule needs every row of the Story frame,
and AD-9 closes `StepContext`'s field list — so the frame's rows and attempts are read once,
in the one place holding both the rows and the repositories, and travel as values on
`RunEnvironment`/`StepPorts` (AD-8).

`frame_anchors` takes the `Git` port rather than the walk's own bundle: it needs exactly one
field of it, and a function that asked for the whole bundle would make this module depend on
the half of `walk.py` that imports it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from orchestrator.application.rules import protected_paths
from orchestrator.application.rules.frames import rows_in_frame
from orchestrator.application.steps.context import RunEnvironment
from orchestrator.application.templates.agent_row import SPEC_FOLDER_KEY
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.git import Git

#: The Run input `initiative@1` binds its epic list under (AD-17's `{initiative_folder}`).
#: `epic@1` and `story@1` declare none, and a Run without one freezes no `epics.yaml`.
INITIATIVE_FOLDER_INPUT = "initiative_folder"


@dataclass(frozen=True)
class WalkFrame:
    """One Story frame as the walker read it: its rows, and every attempt they recorded.

    Read once per row: three questions are asked of it — the commit the frame started at, the
    tests its first attempt froze, the ranges its dispatches recorded — over the same rows.
    """

    rows: tuple[StepRun, ...] = ()
    attempts: tuple[Attempt, ...] = ()


def read_frame(ports: WriterPorts, run_id: UUID, row: StepRun) -> WalkFrame:
    """The row's frame, in plan order then attempt order; empty outside a frame (AD-9)."""
    if row.frame is None:
        return WalkFrame()
    rows = tuple(rows_in_frame(ports.steps.list_for_run(run_id), row.frame))
    return WalkFrame(
        rows=rows,
        attempts=tuple(
            attempt for entry in rows for attempt in ports.attempts.list_for_row(entry.id)
        ),
    )


def frame_anchors(
    git: Git, run: Run, environment: RunEnvironment, frame: WalkFrame
) -> protected_paths.FrameAnchors:
    """AD-17's anchor set and the frame's agent ranges, resolved once for two readers.

    Called from the only place holding both the frame's rows and the repositories (AD-8).
    The tail reads the anchor set off `RunEnvironment`; the commit-guard reaches the whole
    object through the port it already calls.
    """
    return protected_paths.FrameAnchors(
        git=git,
        worktree=Path(run.worktree_path or ""),
        anchors=protected_paths.build(
            spec_folders=_spec_folders(environment, frame.rows),
            initiative_folder=str(run.inputs.get(INITIATIVE_FOLDER_INPUT) or ""),
            frozen_test_files=_frozen_test_files(frame.attempts),
        ),
        ranges=_agent_ranges(frame.attempts),
    )


def frame_start_sha(attempts: Sequence[Attempt]) -> str | None:
    """The commit the row's Story frame started at, in AD-17's own words: the frame's
    lowest-`n` attempt that *has* a `start_sha`. Reading past the attempts that recorded none
    is the whole rule: a Story frame's first row is `git.sync`, which records no commit, so an
    answer taken from the first row that merely *has* an attempt would always be `None`."""
    return next((attempt.start_sha for attempt in attempts if attempt.start_sha is not None), None)


def _spec_folders(environment: RunEnvironment, rows: Sequence[StepRun]) -> tuple[str, ...]:
    """Every spec folder this frame touches: the Run's own input, and each row's resolved one."""
    folders = {environment.spec_folder or ""}
    folders.update(str(row.with_resolved.get(SPEC_FOLDER_KEY) or "") for row in rows)
    return tuple(sorted(folder for folder in folders if folder))


def _frozen_test_files(attempts: Sequence[Attempt]) -> tuple[str, ...]:
    """AD-17: the `frozen_test_files` of the frame's lowest-`n` attempt with a `start_sha`."""
    for attempt in attempts:
        if attempt.start_sha is not None:
            return attempt.frozen_test_files or ()
    return ()


def _agent_ranges(attempts: Sequence[Attempt]) -> tuple[tuple[str, str], ...]:
    """Every agent range the frame recorded: an attempt that started *and* came back.
    `end_sha` is written by the agent tail alone, so an attempt carrying both SHAs is a
    dispatch and nothing else — the scope AD-17 gives the commit-guard."""
    return tuple(
        (attempt.start_sha, attempt.end_sha)
        for attempt in attempts
        if attempt.start_sha is not None and attempt.end_sha is not None
    )
