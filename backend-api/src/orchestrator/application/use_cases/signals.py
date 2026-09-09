"""`handle_signal` (SPEC CAP-9, FR-20, AD-13): the router's one seam into `signal_run` (4.5)
and the `cancel` effects AD-13 lists but 4.5 could not reach.

`signal_run`'s own docstring says why: `Git` and `ProcessRunner` are 4.7/4.8's ports, and
`CancelPlan{pgids, worktrees}` is what it hands back for a later story to act on. This
module is that later story — `kill_group` for every live process, then `remove_worktree`
and, only for a branch this Run created and never pushed, `delete_branch` — all idempotent,
because a Run cancelled twice, or racing its own timeout, must not fail either caller
(AD-13).

**Why this module refuses three of AD-13's ten kinds after `validate` passes.**
`signal_effects.py` already implements every one of the ten correctly — AD-13 is one state
machine, and 4.5 built it whole rather than leaving nine gaps for nine later stories to fill
under the same 100 %-branch bar it was held to. But Epic 4 shipped no surface for
`budget_raise` (no spend to raise against), the three `terminal_*` kinds (no terminal
session), or `continue` on a `protected_path` park (no protected-path rule, Epic 5's). Each
belongs to a later epic's own story: `answer` was the first of them to land — SPEC CAP-1
(6.1) built the `agent` row's resume — `skip_story` the second, with SPEC CAP-4 (6.4),
`skip_epic` the third, with SPEC CAP-5 (6.5), and `budget_raise` together with `continue` on
a `protected_path` park the fourth, with SPEC CAP-6 (6.6). Only the three `terminal_*` kinds
are left, and they are SPEC CAP-7's (6.7). `validate` still runs first, unconditionally: a
signal AD-13 itself refuses gets its own `Conflict` text, never this module's; only a signal
that validation *admits* and this epic does not yet apply is refused here, with the payload
and the state untouched.

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

#: The refusal this module answers with once `validate` has passed but the kind's effect is
#: a later epic's: SPEC CAP-9's own scope is `cancel`, `retry`, and `continue` on the two
#: park kinds this epic's rows can reach without an `agent` step or a protected-path rule.
NOT_AVAILABLE = "{kind} not available yet"

#: `continue`'s three park kinds, all applied. `protected_path` — AD-17's Accept — joined
#: the two this epic started with in SPEC CAP-6 (6.6); 5.6 had already built the executor's
#: whole branch for it (`steps/agent_tail.py::re_check`), which had no caller until the
#: signal could reach it.
CONTINUE_PARK_KINDS: frozenset[ParkKind] = frozenset({"checkpoint", "plan_stale", "protected_path"})

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


@dataclass(frozen=True)
class SignalEffectPorts:
    """What `handle_signal` needs beyond `signal_run`'s own ports: `cancel`'s cleanup."""

    signal: SignalPorts
    git: Git
    process: ProcessRunner
    #: `WORK_DIR`: the root every base clone lives under (AD-14).
    work_dir: str
    read_environment: ReadEnvironment


def _in_scope(kind: SignalKind, park_kind: ParkKind | None) -> bool:
    """The scope built so far: `cancel`, `retry`, `answer`, `skip_story`, `skip_epic` and
    `budget_raise` always; `continue` on all three of its park kinds. `answer` joined the
    list with SPEC CAP-1 (6.1), which built the `agent` row's own resume — the archive, the
    re-dispatch and the prompt clause; `skip_story` joined it with SPEC CAP-4 (6.4),
    `skip_epic` with SPEC CAP-5 (6.5), and `budget_raise` with SPEC CAP-6 (6.6), which also
    admitted `continue` on a `protected_path` park. None of the skips needed a new writer,
    and neither did the Accept: `signal_effects.py`'s own effects and `rules/signals.py::
    VALID` were built whole by 4.5, and 5.6 built the executor's Accept branch — the kinds
    AD-13 has always admitted finally have an effect to reach. Only the three `terminal_*`
    kinds are left (6.7)."""
    if kind in ("cancel", "retry", "answer", "skip_story", "skip_epic", "budget_raise"):
        return True
    return kind == CONTINUE_KIND and park_kind in CONTINUE_PARK_KINDS


def handle_signal(ports: SignalEffectPorts, run_id: UUID, signal: Signal) -> SignalOutcome:
    """Validate against AD-13, refuse what this epic does not apply yet, then apply."""
    _refuse_early(ports.signal, run_id, signal)
    outcome = signal_run(ports.signal, run_id, signal)
    if signal.kind == "cancel" and outcome.cancel_plan is not None:
        _apply_cancel(ports, run_id, outcome.cancel_plan)
    return outcome


def _refuse_early(ports: SignalPorts, run_id: UUID, signal: Signal) -> None:
    """Everything that refuses a signal before a single row moves, in the order it applies.

    `validate` first, so a genuine AD-13 mismatch keeps its own refusal text; then the kinds
    validation admits and this epic has not built; then the Accept's own agreement with the
    hit list the park recorded. `signal_run` re-reads and re-validates everything it writes
    inside its own unit of work — this reads ahead of it rather than writing anything, which
    is why refusing here leaves the Run exactly as it stood.
    """
    writers = ports.writers
    run = require_run(writers, run_id)
    rows = writers.steps.list_for_run(run_id)
    park_row = row_at(rows, run.park_path)
    validate(run, park_row, signal)
    if not _in_scope(signal.kind, run.park_kind):
        raise Conflict(NOT_AVAILABLE.format(kind=signal.kind))
    _refuse_unmatched_accept(ports, run, signal)


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
