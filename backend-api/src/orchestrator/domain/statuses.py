"""The status alphabets and the two state machines every writer goes through (AD-8).

The two dictionaries below are the only encoding of AD-8's two state diagrams. A transition
that is not a key is not a transition: `run_transition` and `step_transition` return the
listed target and raise `InvalidTransition` for everything else, naming the status *and* the
event, so a caller reading the traceback knows which pair it asked for. A function that
returned `None` or fell through to the current status would let a router or an executor
invent a transition the spine does not have, which is exactly what AD-8 exists to prevent.

`InvalidTransition` is deliberately **not** a `DomainError`. `api/errors.py::DOMAIN_STATUS`
maps each `DomainError` kind to an HTTP status, and an unlisted transition has no
operator-facing meaning: `signal_run` validates a signal against the Run's current status
first and raises `Conflict` (409) when it does not apply. Reaching this exception means a
caller skipped that check — a 500 and a bug, not a described outcome.

Every alias here is a `Literal`, and every alias has its `get_args` tuple beside it, so the
tokens are written once. `needs_you` is the stored spelling; the UI renders it `BLK` or
`CHK` from `run.park_kind` and nothing renames it on the way (Consistency Conventions).

The `Gate` here has four tokens where `application/steps/__init__.py::Gate` has three: that
one is the *template-declarable* subset, this one adds `unvalidated`, which the planner
records for a step whose Template declared no gate and which never renders green (NFR-2).
"""

from __future__ import annotations

from typing import Literal, get_args

# ── the alphabets ────────────────────────────────────────────────────────────

#: What a Run's `status` can be.
RunStatus = Literal["queued", "running", "needs_you", "done", "failed", "cancelled"]
RUN_STATUSES: tuple[RunStatus, ...] = get_args(RunStatus)

#: What a `step_run.status` — and the `attempt.status` that reached it — can be.
StepStatus = Literal[
    "planned", "queued", "running", "done", "blocked", "checkpoint", "error", "skipped"
]
STEP_STATUSES: tuple[StepStatus, ...] = get_args(StepStatus)

#: Why a Run stopped for the Operator. Written to `run.park_kind` with the `gate_record`.
ParkKind = Literal[
    "blocked",
    "checkpoint",
    "verify_failed",
    "budget",
    "timeout",
    "push_rejected",
    "protected_path",
    "misconfigured",
    "plan_stale",
    "internal",
    "dependency",
    #: A `git.merge` row whose merge conflicted (AD-13, ratified 2026-09-23). The merge is
    #: left in the worktree for the Operator; the stop admits `retry` and `cancel` only.
    "merge_conflict",
]
PARK_KINDS: tuple[ParkKind, ...] = get_args(ParkKind)

#: What the Operator can send a parked Run (AD-13). `signal_run` owns every one of them.
SignalKind = Literal[
    "answer",
    "continue",
    "retry",
    "skip_step",
    "skip_story",
    "skip_epic",
    "budget_raise",
    "cancel",
    "terminal_start",
    "terminal_release",
    "terminal_resume",
    "start",
]
SIGNAL_KINDS: tuple[SignalKind, ...] = get_args(SignalKind)

#: How a step's success is decided, including the token for a step that declared no gate.
Gate = Literal["liveness", "deterministic", "human", "unvalidated"]
GATES: tuple[Gate, ...] = get_args(Gate)

#: Who a `gate_record` says did the thing it records.
Actor = Literal["operator", "machine", "terminal"]
ACTORS: tuple[Actor, ...] = get_args(Actor)

#: The four events that are neither a park nor a signal: the Run's own beginning and ends.
#: `"started_by_operator"` is distinct from `"start"` — it records the Operator's deferred-
#: start action on a saved Run (story 5-3), while `"start"` is the machine's own running-start
#: record.
LifecycleEvent = Literal["start", "done", "failed", "cancelled", "started_by_operator"]
LIFECYCLE_EVENTS: tuple[LifecycleEvent, ...] = get_args(LifecycleEvent)

#: The bounded re-executions AD-9 records without a Run transition of their own:
#: `redispatch` when a verify failure sends a Run back to an earlier row (4.5),
#: `retry_auto` when a Template's own `retry {max, prompt}` fires (Epic 5). `expired` is
#: not here: AD-13 applies the 30-day `recv` expiry as Run `failed`, which is a lifecycle
#: event the Run already has.
MachineEvent = Literal["redispatch", "retry_auto"]
MACHINE_EVENTS: tuple[MachineEvent, ...] = get_args(MachineEvent)

#: AD-8's own three alphabets, concatenated: what a `gate_record.event` carries for a Run
#: *transition*. The three sets are disjoint, so this is also the full set of them.
GATE_EVENTS: tuple[ParkKind | SignalKind | LifecycleEvent, ...] = (
    *PARK_KINDS,
    *SIGNAL_KINDS,
    *LIFECYCLE_EVENTS,
)

#: A direct worktree write outside `signal_run` and outside an engine step — the brief's own
#: words (story 6-3): "the only worktree writes outside an engine step besides cancel". A
#: third, even-outer layer beside AD-8's three and AD-9's two: `spec_edit` is the Operator's
#: own commit onto a parked Run's worktree, made by `PUT /runs/{id}/files` rather than by any
#: transition the Run itself goes through.
WriteEvent = Literal["spec_edit"]
WRITE_EVENTS: tuple[WriteEvent, ...] = get_args(WriteEvent)

#: What a `gate_record.event` can be: one of AD-8's three, one of AD-9's two bounded
#: re-executions, which are recorded (AD-9: "each is a recorded `attempt` + `gate_record`")
#: without the Run's status moving at all, or one of the direct-write class above.
GateEvent = ParkKind | SignalKind | LifecycleEvent | MachineEvent | WriteEvent
#: **Not** widened to include `WRITE_EVENTS`: `tests/unit/test_gate_events.py` pins this
#: exact concatenation (AD-8's three plus AD-9's two), and `spec_edit` is neither — it is a
#: third, outer layer that only the `GateEvent` *type* needs to admit so `GateRecord(event=
#: "spec_edit", ...)` validates. See story 6-3's Design Notes for why this is not an anchor
#: conflict: `GATE_EVENTS` is already a strict subset the newer alphabet was added beside,
#: never into, and this is the same move one layer further out.
ALL_GATE_EVENTS: tuple[GateEvent, ...] = (*GATE_EVENTS, *MACHINE_EVENTS)

#: What can happen to a Run. `park`, `expire`, `finish` and `fail` are the machine's own
#: words; the rest are the signal kinds that resume or cancel a parked Run.
RunEvent = Literal[
    "start",
    "park",
    "answer",
    "continue",
    "retry",
    "skip_step",
    "skip_story",
    "skip_epic",
    "budget_raise",
    "terminal_resume",
    "expire",
    "finish",
    "fail",
    "cancel",
]
RUN_EVENTS: tuple[RunEvent, ...] = get_args(RunEvent)

#: What can happen to one planned row.
StepEvent = Literal[
    "predecessor_done",
    "skip",
    "start",
    "done",
    "blocked",
    "checkpoint",
    "error",
    "retry",
    "continue_accept",
    "redispatch",
    "answer",
    "terminal_resume",
    "continue",
    "continue_checkpoint",
]
STEP_EVENTS: tuple[StepEvent, ...] = get_args(StepEvent)

#: The Run statuses nothing leaves. No pair in `RUN_TRANSITIONS` starts at one of them.
TERMINAL_RUN: frozenset[RunStatus] = frozenset({"done", "failed", "cancelled"})


# ── the machines ─────────────────────────────────────────────────────────────

#: AD-8's Run diagram, transcribed. `needs_you` resumes on any of the seven signal kinds
#: that mean "carry on"; `expire` is the 30-day recv expiry, and `cancel` applies to every
#: non-terminal status.
RUN_TRANSITIONS: dict[tuple[RunStatus, RunEvent], RunStatus] = {
    ("queued", "start"): "running",
    ("queued", "cancel"): "cancelled",
    ("running", "park"): "needs_you",
    ("running", "finish"): "done",
    ("running", "fail"): "failed",
    ("running", "cancel"): "cancelled",
    ("needs_you", "answer"): "running",
    ("needs_you", "continue"): "running",
    ("needs_you", "retry"): "running",
    ("needs_you", "skip_step"): "running",
    ("needs_you", "skip_story"): "running",
    ("needs_you", "skip_epic"): "running",
    ("needs_you", "budget_raise"): "running",
    ("needs_you", "terminal_resume"): "running",
    ("needs_you", "expire"): "failed",
    ("needs_you", "cancel"): "cancelled",
}

#: AD-8's Step diagram, transcribed. `continue` and `continue_checkpoint` are two events
#: rather than one because a `checkpoint` row's `continue` finishes it while an `agent`
#: row's re-queues it — the kind test that decides which lives in `signal_run`, not here.
STEP_TRANSITIONS: dict[tuple[StepStatus, StepEvent], StepStatus] = {
    ("planned", "predecessor_done"): "queued",
    ("planned", "skip"): "skipped",
    ("queued", "start"): "running",
    ("queued", "skip"): "skipped",
    ("running", "done"): "done",
    ("running", "blocked"): "blocked",
    ("running", "checkpoint"): "checkpoint",
    ("running", "error"): "error",
    ("done", "redispatch"): "queued",
    ("blocked", "answer"): "queued",
    ("blocked", "terminal_resume"): "done",
    ("blocked", "skip"): "skipped",
    ("checkpoint", "continue"): "queued",
    ("checkpoint", "continue_checkpoint"): "done",
    ("checkpoint", "skip"): "skipped",
    ("error", "retry"): "queued",
    ("error", "continue_accept"): "running",
    ("error", "skip"): "skipped",
}


class InvalidTransition(Exception):
    """A `(status, event)` pair neither table lists — a bug in the caller, not an outcome."""


def run_transition(status: RunStatus, event: RunEvent) -> RunStatus:
    """The status a Run in `status` reaches on `event`, or raise naming both tokens."""
    target = RUN_TRANSITIONS.get((status, event))
    if target is None:
        raise InvalidTransition(f"a run in {status} accepts no {event}")
    return target


def step_transition(status: StepStatus, event: StepEvent) -> StepStatus:
    """The status a row in `status` reaches on `event`, or raise naming both tokens."""
    target = STEP_TRANSITIONS.get((status, event))
    if target is None:
        raise InvalidTransition(f"a step in {status} accepts no {event}")
    return target
