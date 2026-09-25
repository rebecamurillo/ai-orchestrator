"""What each Signal does to the rows: AD-13's table, one function per kind.

`signal_run` owns the shape every signal shares — validate, record, move the Run, clear the
park, call the engine — and this module owns what is different about each kind: which rows
change, and which extra Run fields the table lists. An effect returns an `Effect` rather
than writing the Run's status itself, so there is still exactly one place a Run status is
written per signal (AD-8).

**One resume rule.** The table states the row a resumed Run continues at four different
ways — `skip_story` names the frame's `verify` row, or its `git.commit` row when verify was
planned away as `skipped · no quality_gate_command`; `skip_epic` on a rejected push names
the next epic's first row; `continue` on a `checkpoint` row names its successor. All four
are the same sentence: *once the skips are applied, queue the lowest-`seq` row from the
parked one onwards that is neither `done` nor `skipped`*. That is `resume_from`, and it also
answers the case the brief leaves unstated — `skip_epic` on a park outside any Story frame.

**The parked row is the first candidate, not the first row after it.** `skip_story` is
admitted on a `verify_failed` park, whose row *is* the frame's `verify` row — and AD-13
says that row "runs as the re-baseline". A walk that started past the parked row would
leave it `error` inside a Story the Operator has skipped, on a Run that can still reach
`done`. Starting at it re-queues it (`error → retry`), while a parked row the effect has
just marked `skipped` or `done` is stepped over like any other finished row.

**`continue` on a `plan_stale` park is `error → running`.** The brief writes the row as
going to `done` with its successor queued; AD-8's step diagram has no `error → done`, and
AD-13's own `continue` row reads `error → running → routed status` with the effect "the
recorded plan proceeds". The spine binds: `plan_stale` and `protected_path` both apply
`continue_accept`, and the row's own completion later queues the successor through
`apply_step_result`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from orchestrator.application.rules import signals
from orchestrator.application.rules.frames import (
    epic_frame,
    in_frame,
    rows_after,
    rows_in_frame,
    story_frame,
    story_frames_after,
)
from orchestrator.application.steps import (
    AGENT_KIND,
    CHECKPOINT_KIND,
    COMMIT_KIND,
    COMMIT_MESSAGE_KEY,
    LINK_KIND,
    PUSH_KIND,
)
from orchestrator.application.use_cases.writers import (
    FINISHED,
    WriterPorts,
    queue_row,
    set_row,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import SignalKind, StepEvent, step_transition
from orchestrator.domain.values import Signal, Worktree

#: The reason a row skipped by the Operator carries (FR-20, PRD §4.6).
SKIPPED_BY_OPERATOR = "skipped by operator"

#: The commit message a skipped Story's `git.commit` row is re-resolved to.
SKIP_MESSAGE = "story {story_id}: skipped by operator"

#: The row kinds `skip_story` marks skipped inside the current frame (AD-13).
SKIPPABLE_KINDS: frozenset[str] = frozenset({AGENT_KIND, CHECKPOINT_KIND})

#: The row kinds `skip_epic` marks skipped when the rejected push is itself the stop.
REMOTE_KINDS: frozenset[str] = frozenset({PUSH_KIND, LINK_KIND})

#: The row statuses `cancel` marks skipped: the ones that have not started.
UNSTARTED: frozenset[str] = frozenset({"planned", "queued"})

#: The park kind that makes `skip_epic` give up on the epic's push and compare link.
PUSH_REJECTED = "push_rejected"


@dataclass(frozen=True)
class CancelPlan:
    """The worktree and process effects `cancel` leaves to its caller (4.9, AD-13)."""

    #: Every process group a live Attempt of this Run recorded.
    pgids: tuple[int, ...]
    #: Every worktree the Run holds, with the branch each one is on.
    worktrees: tuple[Worktree, ...]


@dataclass(frozen=True)
class Effect:
    """What one signal did to the rows, and what it asks `signal_run` to do to the Run."""

    #: Run fields the table lists beside the status change.
    run_update: dict[str, Any] = field(default_factory=dict)
    #: False when the Run keeps the status it had (the terminal kinds, a held budget raise).
    resume: bool = True
    #: True when the resumed Run has no row left to run and ends `done` instead.
    finished: bool = False
    #: Set by `cancel` only.
    cancel_plan: CancelPlan | None = None


#: One effect: the ports and the Run, the whole plan, the parked row, and the signal.
EffectFn = Callable[[WriterPorts, Run, Sequence[StepRun], StepRun | None, Signal], Effect]


def resume_from(ports: WriterPorts, park_row: StepRun) -> bool:
    """Queue the first unfinished row from the parked one onwards; False when there is none.

    The plan is re-read rather than taken from the caller's list: an effect has just
    written `skipped` or `done` over some of those rows — the parked one included — and
    queueing a stale copy of one would undo the write it was told to apply.
    """
    fresh = ports.steps.list_for_run(park_row.run_id)
    for candidate in rows_after(fresh, park_row.seq - 1):
        if candidate.status in FINISHED:
            continue
        queue_row(ports, candidate)
        return True
    return False


def _parked(park_row: StepRun | None) -> StepRun:
    """The row the Run parked on. A park always names one (`apply_step_result`)."""
    assert park_row is not None
    return park_row


def _skip(ports: WriterPorts, row: StepRun) -> StepRun:
    """Mark one row `skipped` by the Operator, through the machine."""
    return set_row(
        ports,
        row,
        status=step_transition(row.status, "skip"),
        reason=SKIPPED_BY_OPERATOR,
    )


def _answer(
    ports: WriterPorts, _run: Run, _rows: Sequence[StepRun], park_row: StepRun | None, _s: Signal
) -> Effect:
    """The Story is re-dispatched: `blocked → queued`, or `checkpoint → queued` on a reject."""
    row = _parked(park_row)
    event: StepEvent = "answer" if row.status == "blocked" else "continue"
    set_row(ports, row, status=step_transition(row.status, event))
    return Effect()


def _continue(
    ports: WriterPorts, run: Run, rows: Sequence[StepRun], park_row: StepRun | None, signal: Signal
) -> Effect:
    """A `checkpoint` row finishes; an `agent` row re-dispatches; an `error` row resumes."""
    row = _parked(park_row)
    if row.status == "checkpoint":
        if row.kind == CHECKPOINT_KIND:
            set_row(ports, row, status=step_transition(row.status, "continue_checkpoint"))
            return Effect(finished=not resume_from(ports, row))
        set_row(ports, row, status=step_transition(row.status, "continue"))
        return Effect()
    set_row(ports, row, status=step_transition(row.status, "continue_accept"))
    accepted = signals.accepted_files(signal.payload)
    if not accepted:
        return Effect()
    return Effect(run_update={"accepted_paths": run.accepted_paths + accepted})


def _retry(
    ports: WriterPorts, _run: Run, _rows: Sequence[StepRun], park_row: StepRun | None, _s: Signal
) -> Effect:
    """The errored row runs again as a new Attempt: `error → queued`."""
    queue_row(ports, _parked(park_row))
    return Effect()


def _skip_step(
    ports: WriterPorts, _run: Run, _rows: Sequence[StepRun], park_row: StepRun | None, _s: Signal
) -> Effect:
    """Skip the one parked row and resume the Run at the next unfinished row (AD-13, story 1).

    `validate`'s `row_statuses` check handles both refusal cases before this function
    is reached: `dependency` parks have `park_row=None`, and any row whose status is
    outside `{blocked, checkpoint, error}` is refused with a 409 — so `_parked` can
    assert safely here.
    """
    row = _parked(park_row)
    _skip(ports, row)
    return Effect(finished=not resume_from(ports, row))


def _skip_story(
    ports: WriterPorts, _run: Run, rows: Sequence[StepRun], park_row: StepRun | None, _s: Signal
) -> Effect:
    """Skip the Story's remaining agent and checkpoint rows; its verify runs as re-baseline."""
    row = _parked(park_row)
    _skip_frame(ports, rows, row)
    return Effect(finished=not resume_from(ports, row))


def _skip_epic(
    ports: WriterPorts, run: Run, rows: Sequence[StepRun], park_row: StepRun | None, _s: Signal
) -> Effect:
    """Skip the current frame as `skip_story` does, then every remaining frame of the epic."""
    row = _parked(park_row)
    frame = _skip_frame(ports, rows, row)
    for later in story_frames_after(rows, frame) if frame is not None else _all_frames(rows, row):
        for entry in rows_in_frame(rows, later):
            if entry.status not in FINISHED:
                _skip(ports, entry)
    if run.park_kind == PUSH_REJECTED:
        _skip_remote_rows(ports, rows, row)
    elif row.status not in FINISHED and row.kind not in SKIPPABLE_KINDS:
        # AD-13: `skip_epic` also takes the current frame's `error` verify row — the one a
        # `re-baseline failed after skip` parked on. `_skip_frame` leaves it, because
        # `skip_story` needs that row to run; the epic is being given up, so it goes.
        # `row` is the caller's pre-write copy, which is safe here: the only row
        # `_skip_frame` wrote a status to is one of `SKIPPABLE_KINDS`, which this excludes.
        _skip(ports, row)
    return Effect(finished=not resume_from(ports, row))


def _budget_raise(
    ports: WriterPorts, _run: Run, _rows: Sequence[StepRun], park_row: StepRun | None, s: Signal
) -> Effect:
    """The budget rises. A row that was `blocked | checkpoint` keeps the Run parked there;
    any other parked row resumes from itself — a Retry for the one AD-13 leaves `error`, a
    step-over to the next row for the one it leaves `done`.

    **The resume is not optional, and until 6.6 it was missing.** `run_update` alone moves
    the Run to `running` without putting any row on a queue, and `use_cases/walk.py::
    next_row` has exactly three ways of finding work: `first_queued`, a row a signal left
    `running`, and — only while every row is `planned`/`done`/`skipped` — the plan's first
    `planned` row. A budget park on a `done` row satisfies the third by accident. One on an
    `error` row, which is FR-17's retry path (`steps/agent_tail.py::_spend_and_budget` parks
    `budget` on top of the status the row reached), satisfies none of them: the walk fell
    through to `close_run`, which read it as a stall and parked `internal` — a stop that
    admits nothing but `cancel`, on a Run whose only fault was costing money.

    `resume_from` is the call every other resuming effect already makes, and its own rule —
    the parked row is the first candidate — is AD-13's two cases in one line.
    """
    update: dict[str, Any] = {"budget_usd": signals.raised_budget(s.payload)}
    if park_row is None:
        # A Run parked without a row (`Park.path` is optional) has no routed status to keep
        # and no row to resume from; `next_row` starts the plan, as it does from `queued`.
        return Effect(run_update=update)
    if park_row.status in ("blocked", "checkpoint"):
        return Effect(run_update={**update, "park_kind": park_row.status}, resume=False)
    return Effect(run_update=update, finished=not resume_from(ports, park_row))


def _cancel(
    ports: WriterPorts, run: Run, rows: Sequence[StepRun], _row: StepRun | None, _s: Signal
) -> Effect:
    """Every row that has not started is `skipped`; the caller kills and cleans up (4.9)."""
    pgids: list[int] = []
    for entry in rows:
        if entry.status in UNSTARTED:
            _skip(ports, entry)
            continue
        attempt = ports.attempts.get_latest(entry.id)
        if attempt is not None and attempt.pgid is not None and attempt.ended_at is None:
            pgids.append(attempt.pgid)
    plan = CancelPlan(pgids=tuple(pgids), worktrees=run.worktrees)
    return Effect(run_update={"ended_at": ports.clock.now()}, cancel_plan=plan)


def _terminal_start(
    _p: WriterPorts, _run: Run, _rows: Sequence[StepRun], _row: StepRun | None, _s: Signal
) -> Effect:
    """The Operator copied the resume command: the Run's actions are disabled (FR-21)."""
    return Effect(run_update={"terminal_session": True}, resume=False)


def _terminal_release(
    _p: WriterPorts, _run: Run, _rows: Sequence[StepRun], _row: StepRun | None, _s: Signal
) -> Effect:
    """The Operator released the session; the Run's own actions are offered again."""
    return Effect(run_update={"terminal_session": False}, resume=False)


def _terminal_resume(
    ports: WriterPorts, _run: Run, rows: Sequence[StepRun], park_row: StepRun | None, _s: Signal
) -> Effect:
    """Two clean polls found the Story done in the terminal: `blocked → done`, verify next."""
    row = _parked(park_row)
    set_row(ports, row, status=step_transition(row.status, "terminal_resume"))
    queued = resume_from(ports, row)
    return Effect(run_update={"terminal_session": False}, finished=not queued)


def _skip_frame(ports: WriterPorts, rows: Sequence[StepRun], park_row: StepRun) -> str | None:
    """`skip_story`'s own body: the frame's agent and checkpoint rows, and its commit message."""
    frame = story_frame(park_row.path)
    if frame is None:
        return None
    for entry in rows_in_frame(rows, frame):
        if entry.kind in SKIPPABLE_KINDS and entry.status not in FINISHED:
            _skip(ports, entry)
        elif entry.kind == COMMIT_KIND and entry.status not in FINISHED:
            _rewrite_commit_message(ports, entry)
    return frame


def _rewrite_commit_message(ports: WriterPorts, row: StepRun) -> None:
    """The skipped Story still commits whatever is on the tree, under the Operator's words."""
    message = SKIP_MESSAGE.format(story_id=row.story_id)
    set_row(ports, row, with_resolved={**row.with_resolved, COMMIT_MESSAGE_KEY: message})


def _all_frames(rows: Sequence[StepRun], park_row: StepRun) -> list[str]:
    """Every later Story frame of the parked row's epic — `skip_epic` outside a Story frame.

    Only reached when the parked row is in no Story frame of its own, so starting after it
    loses nothing: there is no frame it belongs to that this would have to include.
    """
    epic = epic_frame(park_row.path)
    seen: list[str] = []
    for entry in rows_after(rows, park_row.seq):
        frame = story_frame(entry.path)
        if frame is None or frame in seen:
            continue
        if epic is not None and not in_frame(frame, epic):
            continue
        seen.append(frame)
    return seen


def _skip_remote_rows(ports: WriterPorts, rows: Sequence[StepRun], park_row: StepRun) -> None:
    """A rejected push takes the epic's compare link with it: both rows are `skipped`."""
    _skip(ports, park_row)
    epic = epic_frame(park_row.path)
    for entry in rows_after(rows, park_row.seq):
        if epic is not None and not in_frame(entry.path, epic):
            break
        if entry.kind not in REMOTE_KINDS or entry.status in FINISHED:
            break
        _skip(ports, entry)


#: One row of AD-13's table per kind, in the table's own order.
EFFECTS: dict[SignalKind, EffectFn] = {
    "answer": _answer,
    "continue": _continue,
    "retry": _retry,
    "skip_step": _skip_step,
    "skip_story": _skip_story,
    "skip_epic": _skip_epic,
    "budget_raise": _budget_raise,
    "cancel": _cancel,
    "terminal_start": _terminal_start,
    "terminal_release": _terminal_release,
    "terminal_resume": _terminal_resume,
}
