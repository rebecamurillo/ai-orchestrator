"""The epic/story arithmetic both read models share: progress, the Story cells, the summary.

Split out of `run_views.py` for the reason `run_views_alert.py` was (6.2): that module was
at 389 of the 400 lines `tests/unit/test_source_limits.py` allows, and this story widens
the summary's own skipped list. The seam is real rather than arbitrary — everything here is
a pure function of `(run, rows)` counting frames, while `run_views.py` keeps the assembly
that reads ports. The private names stay bound in `run_views.py` (`_progress = progress`,
…), so every existing call site resolves unchanged.

**What `summary.skipped` names, and why the commit-guard row cannot answer it** (FR-11,
FR-20, SM-C3). `skip_epic` marks a whole later frame `skipped`, its `git.commit` row
included, so that row's own status was enough while skipping an epic was the only way a
Story got skipped. `skip_story` is the opposite by design: it leaves the frame's commit-guard
runnable — with the message re-resolved to `story {id}: skipped by operator` — so the
leftovers still land on the branch before the next Story starts, and that row therefore
reaches `done`. The durable record that the *Operator* skipped the frame is the reason on
the rows the signal did mark: `signal_effects.py::SKIPPED_BY_OPERATOR`. Reading the reason,
not the status alone, is what keeps `skipped · no quality_gate_command` and the `skipped`
rows an already-done Story leaves behind out of the list.

The Board card's `m/m` is deliberately *not* narrowed to match: `stories_done` counts every
commit-guard row that settled, so a skipped Story reads complete and is named beside the
compare link instead (FR-20's own `[ASSUMPTION]`, and what keeps the strip's own per-epic
count in step with the card's).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from uuid import UUID

from orchestrator.application.rules.frames import epic_frame, rows_in_frame, story_frame
from orchestrator.application.steps import COMMIT_KIND, PUSH_KIND
from orchestrator.application.use_cases.run_view_types import (
    Progress,
    StoryCell,
    Summary,
)
from orchestrator.application.use_cases.signal_effects import SKIPPED_BY_OPERATOR
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun

#: The two Templates whose Runs carry epic/story progress (SPEC CAP-12). Every other
#: Template — `repo-init` today — has no `epics[i]`/`stories[j]` frame in any of its rows.
PROGRESS_TEMPLATES = ("epic", "initiative")

#: The statuses that finish a frame's own row, one way or the other (AD-9's own pair).
SETTLED: tuple[str, ...] = ("done", "skipped")

BRACKET_INDEX = re.compile(r"\[(\d+)\]$")


def progress(run: Run, rows: Sequence[StepRun]) -> Progress | None:
    """`None` for a Run whose Template has no epic/story frame at all (e.g. `repo-init`)."""
    if run.template_name not in PROGRESS_TEMPLATES:
        return None
    story_commits = [row for row in rows if row.kind == COMMIT_KIND]
    stories_total = len(story_commits)
    stories_done = sum(1 for row in story_commits if row.status in SETTLED)
    epics_total: int | None = None
    epics_done: int | None = None
    if run.template_name == "initiative":
        epic_pushes = [row for row in rows if row.kind == PUSH_KIND]
        epics_total = len(epic_pushes)
        epics_done = sum(1 for row in epic_pushes if row.status in SETTLED)
    return Progress(
        epics_done=epics_done,
        epics_total=epics_total,
        stories_done=stories_done,
        stories_total=stories_total,
        links=len(run.compare_urls),
    )


def story_cells(
    run: Run, rows: Sequence[StepRun], attempts_by_row: Mapping[UUID, Sequence[Attempt]]
) -> list[StoryCell]:
    """One cell per story frame, in plan order — state off the frame's own commit-guard row."""
    commit_rows = sorted((row for row in rows if row.kind == COMMIT_KIND), key=lambda row: row.seq)
    cells = []
    for commit_row in commit_rows:
        frame = story_frame(commit_row.path)
        if frame is None:
            continue
        frame_cost = Decimal("0")
        for frame_row in rows_in_frame(rows, frame):
            for attempt in attempts_by_row.get(frame_row.id, ()):
                frame_cost += attempt.cost_usd or Decimal("0")
        cells.append(_story_cell(run, rows, frame, commit_row, frame_cost))
    return cells


def summary(run: Run, rows: Sequence[StepRun]) -> Summary | None:
    """The `done` Run's own line: the progress, the compare links, and what was skipped."""
    if run.status != "done":
        return None
    return Summary(
        progress=progress(run, rows),
        links=list(run.compare_urls),
        skipped=skipped_stories(rows),
        skipped_epics=skipped_epics(rows),
    )


def skipped_stories(rows: Sequence[StepRun]) -> list[str]:
    """Every Story id the Run did not build, in plan order (see this module's own docstring).

    Two ways a frame gets here, and both are read off the frame rather than off one row: its
    commit-guard row is itself `skipped` (nothing of the Story ran at all), or the Operator
    skipped it and its rows carry `SKIPPED_BY_OPERATOR` while the commit-guard still ran.

    `summary` is the only caller and it answers `None` for a Run that is not `done`, which is
    what keeps `cancel` out of this: that signal marks every unstarted row skipped under the
    same reason, and a cancelled Run would otherwise read as one that skipped every Story it
    had not reached yet.
    """
    listed: list[str] = []
    for row in rows:
        if row.kind != COMMIT_KIND or row.story_id is None:
            continue
        frame = story_frame(row.path)
        if row.status == "skipped" or (frame is not None and _operator_skipped(rows, frame)):
            listed.append(row.story_id)
    return listed


def skipped_epics(rows: Sequence[StepRun]) -> list[int]:
    """Every epic number `skip_epic` gave up the push on, in plan order (6.5, FR-20).

    Mirrors `skipped_stories`'s own read of the reason, not only the status: `cancel` also
    marks every unstarted row `skipped` under the same `SKIPPED_BY_OPERATOR` reason, and
    `summary` is the only caller — it already answers `None` for a Run that is not `done`,
    which is what keeps a cancelled Run's own unstarted `push` rows out of this list too.

    Numbered `bracket_index(epic) + 1` — the brief's own 1-based convention (`epics[0]` is
    "epic 1"), distinct from `StoryCell.epic_index`'s pre-existing 0-based one. A plain
    `epic`-template Run's own `push` row carries no `epics[n]` frame at all
    (`epic_frame` answers `None`), so it is never numbered here — consistent with `progress
    ()`'s own `epics_total=None` treatment of that Template: `skip_epic` still skips such a
    Run's push (`signal_effects.py::_skip_remote_rows`), this list just cannot count it.
    """
    listed: list[int] = []
    for row in rows:
        if row.kind != PUSH_KIND:
            continue
        epic = epic_frame(row.path)
        if epic is None:
            continue
        if row.status == "skipped" and row.reason == SKIPPED_BY_OPERATOR:
            listed.append(bracket_index(epic) + 1)
    return listed


def _operator_skipped(rows: Sequence[StepRun], frame: str) -> bool:
    """Whether any row of `frame` carries the reason only an Operator's skip writes."""
    return any(
        row.status == "skipped" and row.reason == SKIPPED_BY_OPERATOR
        for row in rows_in_frame(rows, frame)
    )


def _story_cell(
    run: Run, rows: Sequence[StepRun], frame: str, commit_row: StepRun, cost_usd: Decimal
) -> StoryCell:
    epic = epic_frame(frame)
    epic_index = bracket_index(epic) if epic is not None else 0
    if commit_row.status == "skipped":
        state = "skipped"
    elif commit_row.status == "done":
        state = "done"
    elif _frame_is_current(run, rows, frame):
        state = "current"
    else:
        state = "future"
    return StoryCell(
        epic_index=epic_index, story_id=commit_row.story_id or "", state=state, cost_usd=cost_usd
    )


def _frame_is_current(run: Run, rows: Sequence[StepRun], frame: str) -> bool:
    """The same "current" concept `application/graph.py::_is_current` states per row, here
    over a whole frame: any member is running, or is the parked row (guarded on
    `park_path is not None` for the same reason that function is, even though `row.path`
    being a non-empty `str` already makes `row.path == None` impossible)."""
    return any(
        row.status == "running" or (run.park_path is not None and row.path == run.park_path)
        for row in rows
        if row.path == frame or row.path.startswith(f"{frame}.")
    )


def bracket_index(prefix: str) -> int:
    match = BRACKET_INDEX.search(prefix)
    return int(match.group(1)) if match else 0
