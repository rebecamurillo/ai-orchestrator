"""`handle_signal` (SPEC CAP-9, FR-20, AD-13): the router's one seam into `signal_run` (4.5)
and the `cancel` effects AD-13 lists but 4.5 could not reach.

`signal_run`'s own docstring says why: `Git` and `ProcessRunner` are 4.7/4.8's ports, and
`CancelPlan{pgids, worktrees}` is what it hands back for a later story to act on. This
module is that later story — `kill_group` for every live process, then `remove_worktree`
and, only for a branch this Run created and never pushed, `delete_branch` — all idempotent,
because a Run cancelled twice, or racing its own timeout, must not fail either caller
(AD-13).

**This module used to refuse the kinds Epic 4 had built no surface for, and no longer does.**
`signal_effects.py` implemented all ten of AD-13's kinds correctly from 4.5 — AD-13 is one
state machine, and 4.5 built it whole rather than leaving nine gaps for nine later stories to
fill under the same 100 %-branch bar it was held to. What Epic 4 shipped no *surface* for was
`answer`, the two skips, `budget_raise`, `continue` on a `protected_path` park, and the three
`terminal_*` kinds, so a scope gate here answered each of them `{kind} not available yet`
until its own story landed: SPEC CAP-1 (6.1), CAP-4 (6.4), CAP-5 (6.5), CAP-6 (6.6) and
CAP-7 (6.7) took them in that order. 6.7 landed the last three, at which point the gate
admitted every kind unconditionally — `validate` already refuses `continue` outside its own
three park kinds, so the one conditional arm was unreachable too — and a predicate that
cannot say no is a comment pretending to be a check. It was removed with the story that
emptied it; `validate` is now the whole of the refusal, and it still runs first and
unconditionally, so a signal AD-13 itself refuses gets its own `Conflict` text with the
payload and the state untouched.

**A terminal session refuses every action but its own (6.7, FR-21).** While
`run.terminal_session` is true the Operator is working in the agent's own session in a
terminal, and two writers moving the same row would be exactly the "applied twice or
half-way" AD-8 forbids. The read model already drops those actions
(`rules/signals.py::run_admitted_signals`), and this is the same rule stated where it can be
enforced: a client that posts one anyway — a stale tab, a script — is refused with the
sentence that says how to get them back. It is not a row of AD-13's table because the table
is keyed on the park kind and the row's status, and a terminal session is neither; it is a
fact about the Run, the same shape as the Accept's own check below.

**The Accept has a second refusal of its own (6.6, FR-31).** `continue` on a
`protected_path` park is the one signal whose payload has to agree with something the Run
already wrote down: the files an Operator accepts are exactly the files AD-17 reported, kept
on that park's own gate record. A shorter list would leave a hit unaccepted and park the
resumed tail on the same file again; a longer one would record an acceptance the Run never
asked for, and `run.accepted_paths` is what AD-17 subtracts on every later check of the
frame. Neither is a mismatch AD-13's table can see — it is keyed on statuses and kinds, not
on a payload against stored state — so it is checked here, before anything is written.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from orchestrator.application.rules.protected_paths import hit_paths, park_record_payload
from orchestrator.application.rules.signals import accepted_files, row_at, validate
from orchestrator.application.steps.context import RunEnvironment
from orchestrator.application.use_cases.signal_effects import CancelPlan
from orchestrator.application.use_cases.signal_run import SignalOutcome, SignalPorts, signal_run
from orchestrator.application.use_cases.writers import require_run
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.process import ProcessRunner
from orchestrator.domain.statuses import ParkKind, SignalKind
from orchestrator.domain.values import Signal

#: One Run's environment, resolved for `cancel`'s cleanup — the same shape
#: `infrastructure/dbos/walker.py::ReadEnvironment` reads a row's own environment through.
#: Declared again here rather than imported: that module is `infrastructure/`, and AD-2
#: forbids this one reaching back into it for a type alias alone.
ReadEnvironment = Callable[[UUID], RunEnvironment | None]

#: The one kind and park whose payload is checked against stored state — see the module
#: docstring's second paragraph.
CONTINUE_KIND: SignalKind = "continue"
PROTECTED_PATH: ParkKind = "protected_path"

#: What an Accept whose list is not the park's own hit list is refused with, and what a park
#: that recorded no hit list at all is refused with. The second is not reachable from a park
#: this system writes today — both call sites of AD-17's rule record their hits
#: (`rules/protected_paths.py::hits_payload`) — but a Run parked by an older backend carries
#: no such payload, and silently accepting nothing there would resume the tail onto the very
#: files it stopped for.
ACCEPT_MISMATCH = "accepted files must be exactly the protected paths: {hits}"
ACCEPT_NO_HITS = "no protected paths were recorded on this park"

#: The only kinds a Run with a terminal session in progress still applies (6.7, FR-21) — the
#: same set `rules/signals.py::TERMINAL_SESSION_SIGNALS` offers, plus the one the poll job
#: sends. `terminal_start` is absent on purpose: `validate` refuses a second start with
#: AD-13's own sentence before this check is ever reached, and that sentence is the better
#: one there.
TERMINAL_SESSION_KINDS: frozenset[SignalKind] = frozenset(
    {"cancel", "terminal_release", "terminal_resume"}
)

#: What everything else is refused with while the session is open. It names the mechanism and
#: the way out (NFR-8) rather than restating the state.
IN_TERMINAL_SESSION = "terminal session in progress: Release it before {kind}"


@dataclass(frozen=True)
class SignalEffectPorts:
    """What `handle_signal` needs beyond `signal_run`'s own ports: `cancel`'s cleanup."""

    signal: SignalPorts
    git: Git
    process: ProcessRunner
    #: `WORK_DIR`: the root every base clone lives under (AD-14).
    work_dir: str
    read_environment: ReadEnvironment


def handle_signal(ports: SignalEffectPorts, run_id: UUID, signal: Signal) -> SignalOutcome:
    """Validate against AD-13, check the Accept's own agreement, then apply the effect."""
    _refuse_early(ports.signal, run_id, signal)
    outcome = signal_run(ports.signal, run_id, signal)
    if signal.kind == "cancel" and outcome.cancel_plan is not None:
        _apply_cancel(ports, run_id, outcome.cancel_plan)
    return outcome


def _refuse_early(ports: SignalPorts, run_id: UUID, signal: Signal) -> None:
    """Everything that refuses a signal before a single row moves, in the order it applies.

    `validate` first, so a genuine AD-13 mismatch keeps its own refusal text; then the
    terminal session, which holds every action but its own; then the Accept's own agreement
    with the hit list the park recorded. `signal_run` re-reads and re-validates everything it
    writes inside its own unit of work — this reads ahead of it rather than writing anything,
    which is why refusing here leaves the Run exactly as it stood.
    """
    writers = ports.writers
    run = require_run(writers, run_id)
    rows = writers.steps.list_for_run(run_id)
    park_row = row_at(rows, run.park_path)
    validate(run, park_row, signal, rows)
    _refuse_during_terminal_session(run, signal)
    _refuse_unmatched_accept(ports, run, signal)


def _refuse_during_terminal_session(run: Run, signal: Signal) -> None:
    """FR-21: the terminal holds the Run until it is released, cancelled, or resumed."""
    if run.terminal_session and signal.kind not in TERMINAL_SESSION_KINDS:
        raise Conflict(IN_TERMINAL_SESSION.format(kind=signal.kind))


def _refuse_unmatched_accept(ports: SignalPorts, run: Run, signal: Signal) -> None:
    """FR-31: an Accept names exactly the files AD-17 reported, or it is a 409.

    Compared as sets: the Operator is answering "yes to these files", and the order the two
    lists happen to be in says nothing about that. The hit list comes off the park's own
    gate record rather than off `run.park_reason`, because the record is append-only and
    already carries the kinds the screen renders (`rules/protected_paths.py`).
    """
    if signal.kind != CONTINUE_KIND or run.park_kind != PROTECTED_PATH:
        return
    hits = hit_paths(park_record_payload(ports.writers.records.list_for_run(run.id), run))
    if not hits:
        raise Conflict(ACCEPT_NO_HITS)
    if set(accepted_files(signal.payload)) != set(hits):
        raise Conflict(ACCEPT_MISMATCH.format(hits=", ".join(hits)))


def _apply_cancel(ports: SignalEffectPorts, run_id: UUID, plan: CancelPlan) -> None:
    """AD-13's `cancel` effects `signal_run` could not reach: kill, remove, delete.

    Every step is idempotent (the ports' own contracts): a `pgid` already gone, a worktree
    already removed, a branch already gone are none of them a failure — cancelling a Run
    and a timeout racing each other must both land cleanly.
    """
    for pgid in plan.pgids:
        ports.process.kill_group(pgid)
    env = ports.read_environment(run_id)
    if env is None:
        return
    base = env.base_dir(ports.work_dir)
    for worktree in plan.worktrees:
        ports.git.remove_worktree(base, Path(worktree.path))
        if worktree.created_branch and not worktree.pushed:
            ports.git.delete_branch(base, worktree.branch)
