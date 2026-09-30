"""Frames: which rows belong to a Story, which belong to an epic, and what comes after.

A *frame* is the loop prefix the planner wrote on a row — `stories[0]`,
`epics[1].stories[3]` — and `StepRun.frame` carries the innermost one (4.2). `skip_story`
and `skip_epic` are stated in frames rather than in rows (AD-13), so every question they
ask is answered here, over a plain list of rows, rather than inside the use case.

Two shapes matter and they are read off the path, not off `frame`, because a row outside a
Story loop still belongs to its epic: `story_frame("epics[1].stories[3].build")` is
`epics[1].stories[3]` and `epic_frame` of the same path is `epics[1]`, while
`epic_frame("epics[1].push")` is also `epics[1]` although that row's `frame` is `epics[1]`
and its `story_frame` is `None`.

Step ids are used verbatim in a path and may contain hyphens (`stories[0].commit-guard`),
so nothing here splits on anything but the bracket that closes a loop index.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from orchestrator.domain.entities.step_run import StepRun

#: The loop segment the planner writes: an `as` name, then the item's index in brackets.
#: `stories` and `epics` are the two the shipped Templates use and the two AD-13 names.
_SEGMENT = re.compile(r"^(?P<name>[^.\[\]]+)\[(?P<index>\d+)\]$")

#: The loop whose frame `skip_story` acts on.
STORIES = "stories"

#: The loop whose frame `skip_epic` acts on.
EPICS = "epics"


def _prefix_through(path: str, name: str) -> str | None:
    """The prefix of `path` up to and including the last `{name}[i]` segment, or `None`."""
    segments = path.split(".")
    for index in range(len(segments) - 1, -1, -1):
        match = _SEGMENT.match(segments[index])
        if match is not None and match["name"] == name:
            return ".".join(segments[: index + 1])
    return None


def story_frame(path: str) -> str | None:
    """The innermost `…stories[n]` prefix of `path`, or `None` outside a Story frame."""
    return _prefix_through(path, STORIES)


def epic_frame(path: str) -> str | None:
    """The `…epics[n]` prefix of `path`, or `None` when the path is in no epic frame."""
    return _prefix_through(path, EPICS)


def in_frame(path: str, frame: str) -> bool:
    """Whether `path` is `frame` itself or a row nested under it.

    The separator is part of the comparison, which is the whole point: a bare
    `path.startswith(frame)` would put `stories[10].build` inside `stories[1]`.
    """
    return path == frame or path.startswith(f"{frame}.")


def rows_in_frame(rows: Iterable[StepRun], frame: str) -> list[StepRun]:
    """Every row of `frame`, in `seq` order — the rows a skip signal acts on."""
    return sorted((row for row in rows if in_frame(row.path, frame)), key=_seq)


def story_frames_after(rows: Sequence[StepRun], frame: str) -> list[str]:
    """The Story frames of `frame`'s epic that start after `frame`, in plan order.

    `frame` is a Story frame; the epic is its own `epics[n]` prefix, or the whole Run when
    the plan has no epic loop. What comes back are frame prefixes, not rows: `skip_epic`
    skips *every* row of each of them, while it treats the current frame like `skip_story`.
    """
    epic = epic_frame(frame)
    seen: list[str] = []
    for row in sorted(rows, key=_seq):
        other = story_frame(row.path)
        if other is None or other == frame or other in seen:
            continue
        if epic is not None and not in_frame(other, epic):
            continue
        if _first_seq(rows, other) > _first_seq(rows, frame):
            seen.append(other)
    return seen


def run_is_one_epic(rows: Sequence[StepRun]) -> bool:
    """Whether the whole Run is one epic, so `skip_epic` applies with no `epics[i]` frame.

    Read off the plan, never off the root Template's name (Operator decision 2026-09-30: no
    template name hardcoded in product code). A Run is one epic when its rows loop over
    Stories and over nothing above them: some row sits in a `stories[n]` frame, and no row
    sits in an `epics[n]` one. A Run with an epic loop is several epics and `skip_epic` has
    that frame to act on; a Run with neither loop (an initialisation Run) is no epic at all
    and the signal has nothing to skip.

    This is the widening AD-13 does not state. AD-13 says only "`park_path` inside an
    `epics[i]` frame"; PRD §4.6 offers *Skip epic* on nine of the ten stops without
    excluding a single-epic Run, and such a Run has no `epics[i]` segment in any path, so
    the spine's rule alone would make the action permanently unavailable on the very shape
    it is most obviously for. The 4.5 brief's widening is followed, and flagged here rather
    than silently generalised — it is now stated over the plan, which is what lets a
    Template of any name get the same answer for the same shape.
    """
    if any(epic_frame(row.path) is not None for row in rows):
        return False
    return any(story_frame(row.path) is not None for row in rows)


def rows_after(rows: Iterable[StepRun], seq: int) -> list[StepRun]:
    """Every row after `seq`, in `seq` order — where a resumed Run looks for its next row."""
    return sorted((row for row in rows if row.seq > seq), key=_seq)


def _first_seq(rows: Iterable[StepRun], frame: str) -> int:
    """The `seq` of `frame`'s first row: a frame's position in the plan is its first row's."""
    return min(row.seq for row in rows if in_frame(row.path, frame))


def _seq(row: StepRun) -> int:
    return row.seq
