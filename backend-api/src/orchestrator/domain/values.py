"""The value objects executors, the planner and the Operator's signals speak in.

None of them is stored on its own and none of them has behaviour: they exist so the things
that cross a boundary in Epic 4 cross it as one object with named parts rather than as a
handful of positional arguments a caller could reorder. All are frozen, so a `StepResult`
an executor returned cannot be edited by the walker that received it — AD-8's "executors
never write a status" is a property of the type here, not a convention to remember.

`StepResult.gate` is the domain `Gate` (four tokens, `unvalidated` included), because the
result carries what the planner recorded for the row, not what the Template was allowed to
declare. `PlannedRow.kind` is a plain `str`: `application/steps/__init__.py::KIND_META` is
the only enumeration of kinds (AD-9) and `domain/` may not import `application/` (AD-2).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.domain.statuses import Gate, ParkKind, SignalKind, StepStatus


class Park(BaseModel):
    """Why a Run stops for the Operator, and where. `path` is the row that stopped it."""

    model_config = ConfigDict(frozen=True)

    kind: ParkKind
    reason: str
    #: `None` for a stop that belongs to the Run rather than to one row — a raised budget,
    #: for instance, is not about a step.
    path: str | None = None


class Redispatch(BaseModel):
    """A completed row asking the walker to go back to an earlier one, boundedly (AD-9)."""

    model_config = ConfigDict(frozen=True)

    #: The `step_run.seq` to re-queue.
    target_seq: int
    #: How many times this redispatch may fire before the Run parks instead.
    max: int


class Retry(BaseModel):
    """A Template's own bounded re-run of the row that just failed (AD-9, FR-16).

    `Redispatch`'s sibling, and deliberately its shape: both are a completed row asking the
    walker for one more bounded execution, and neither carries a status — `apply_step_result`
    counts the attempt, records it and re-queues the row (AD-8). The difference is where the
    Run goes: a redispatch names an *earlier* row, a retry is this row again.

    `prompt` is what the next attempt is told, resolved at plan time (AD-7): a prompt naming
    `{{story.id}}` had to be filled in from the branch the plan was made on, not from
    whatever the branch says an hour later.
    """

    model_config = ConfigDict(frozen=True)

    #: What the next attempt is asked, in front of the dispatch prompt or on its own.
    prompt: str
    #: How many times the row may re-run before it parks instead.
    max: int
    #: Whether the harness should continue the same session, where it can (AD-10).
    resume_session: bool = True


class Worktree(BaseModel):
    """One worktree a Run created, and what happened to the branch in it."""

    model_config = ConfigDict(frozen=True)

    branch: str
    path: str
    #: True when this Run created the branch rather than checking out an existing one.
    created_branch: bool
    #: True once `git.push` has landed it on the origin.
    pushed: bool


class RunUpdates(BaseModel):
    """The Run's own columns a result asks `apply_step_result` to write (AD-8, AD-14).

    Three kinds have a side effect on the Run itself rather than only on their row —
    `git.worktree` sets `worktree_path` and appends to `worktrees[]`, `git.push` marks the
    entry `pushed`, `pr.link` appends to `compare_urls[]` — and AD-8 gives an executor no way
    to write one. It returns this instead, and the writer applies it inside the unit of work
    it already opened, so the next row reads a committed value.

    Every field is `None` for "this result says nothing about that column", which is not the
    same as an empty tuple: a `pr.link` on a host with no compare URL leaves the list alone
    rather than replacing it with nothing.
    """

    model_config = ConfigDict(frozen=True)

    worktree_path: str | None = None
    worktrees: tuple[Worktree, ...] | None = None
    compare_urls: tuple[str, ...] | None = None


class StepResult(BaseModel):
    """What a `StepExecutor` returns: the status the row reached and what came with it."""

    model_config = ConfigDict(frozen=True)

    status: StepStatus
    gate: Gate
    #: A log path or a short output, whichever the kind produced; `None` when it produced
    #: neither.
    output_ref: str | None = None
    #: The file `ProcessRunner.start` appended this row's stdout and stderr into, written to
    #: `attempt.log_path` by `apply_step_result` — the column `latest.log_tail` is read from.
    #: Set only by a kind that started a process, and only on a result of that process, so
    #: the reader is never handed a path to a file nothing wrote. It is deliberately not
    #: `output_ref`: `git.commit` puts a sha there and `pr.link` a URL. `None` is "this
    #: result says nothing about a log", never "this attempt has none" — the `agent` kind
    #: records its own through `mark_finished` before this result is ever applied.
    log_path: str | None = None
    #: Set when the result stops the Run — `apply_step_result` writes `run.park_kind`,
    #: `run.park_path` and the `gate_record` together from it (AD-8).
    park: Park | None = None
    #: Set only alongside `park` (AD-11, FR-17): a routed stop (`blocked`, `checkpoint`, …)
    #: that is *also* over budget keeps its own record and gets a second one for this, and
    #: `run.park_kind` is rewritten to `budget` after it — `apply_step_result`'s own
    #: `after_route` seam, because the machine has no `(needs_you, park)` pair to re-enter.
    budget_park: Park | None = None
    #: Set only by a kind that routes backwards on failure.
    redispatch: Redispatch | None = None
    #: Set only by a kind whose Template declared a `retry` contract and whose row has not
    #: used it up; `None` on every result that is not asking to run again (FR-16).
    retry: Retry | None = None
    #: The sentence the Operator reads on the row.
    reason: str | None = None
    #: The Run's own columns this result asks the writer to set; `None` when it asks for none.
    run_updates: RunUpdates | None = None
    #: Whatever the stop needs kept on its gate record — AD-17's list of the protected paths
    #: an attempt touched, so the Operator and 5.9's trajectory read the files and not only
    #: the sentence. Written by `apply_step_result` alongside the park (AD-8); `{}` on every
    #: result that carries nothing, and built per instance so two results never share one.
    payload: dict[str, Any] = Field(default_factory=dict)


class Signal(BaseModel):
    """One operator action on a Run (AD-13). `signal_run` is the only thing that applies it."""

    model_config = ConfigDict(frozen=True)

    kind: SignalKind
    #: Whatever the kind carries — an answer's text, a raised budget, the accepted files.
    #: A mapping rather than `None`, so no caller has to guard the empty case; built per
    #: instance, so two signals never share one.
    payload: dict[str, Any] = Field(default_factory=dict)


class PlannedRow(BaseModel):
    """One row of a plan, as `plan_run` produces it before any of it is stored (AD-7)."""

    model_config = ConfigDict(frozen=True)

    seq: int
    path: str
    label: str
    kind: str
    gate: Gate
    status: StepStatus
    reason: str | None
    with_resolved: dict[str, Any]
    #: The innermost `…stories[n]` / `epics[n]` prefix of `path`, or `None` outside a frame.
    frame: str | None
    story_id: str | None
