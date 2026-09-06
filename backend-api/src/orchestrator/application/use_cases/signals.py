"""`handle_signal` (SPEC CAP-9, FR-20, AD-13): the router's one seam into `signal_run` (4.5)
and the `cancel` effects AD-13 lists but 4.5 could not reach.

`signal_run`'s own docstring says why: `Git` and `ProcessRunner` are 4.7/4.8's ports, and
`CancelPlan{pgids, worktrees}` is what it hands back for a later story to act on. This
module is that later story — `kill_group` for every live process, then `remove_worktree`
and, only for a branch this Run created and never pushed, `delete_branch` — all idempotent,
because a Run cancelled twice, or racing its own timeout, must not fail either caller
(AD-13).

**Why this module refuses seven of AD-13's ten kinds after `validate` passes.**
`signal_effects.py` already implements every one of the ten correctly — AD-13 is one state
machine, and 4.5 built it whole rather than leaving nine gaps for nine later stories to fill
under the same 100 %-branch bar it was held to. But this epic ships no surface for
`answer` (no `agent` step to answer), `skip_story`/`skip_epic` (nothing to skip yet),
`budget_raise` (no spend to raise against), the three `terminal_*` kinds (no terminal
session), or `continue` on a `protected_path` park (no protected-path rule, Epic 5's). Each
belongs to a later epic's own story. `validate` still runs first, unconditionally: a signal
AD-13 itself refuses gets its own `Conflict` text, never this module's; only a signal that
validation *admits* and this epic does not yet apply is refused here, with the payload and
the state untouched.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from orchestrator.application.rules.signals import row_at, validate
from orchestrator.application.steps.context import RunEnvironment
from orchestrator.application.use_cases.signal_effects import CancelPlan
from orchestrator.application.use_cases.signal_run import SignalOutcome, SignalPorts, signal_run
from orchestrator.application.use_cases.writers import require_run
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

#: `continue`'s two park kinds this epic applies. AD-13's third, `protected_path`, is Epic
#: 5's accepted-files flow — refused here the same as any other kind not yet built.
CONTINUE_PARK_KINDS: frozenset[ParkKind] = frozenset({"checkpoint", "plan_stale"})


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
    """SPEC CAP-9's own scope: `cancel` and `retry` always; `continue` on two park kinds."""
    if kind in ("cancel", "retry"):
        return True
    return kind == "continue" and park_kind in CONTINUE_PARK_KINDS


def handle_signal(ports: SignalEffectPorts, run_id: UUID, signal: Signal) -> SignalOutcome:
    """Validate against AD-13, refuse what this epic does not apply yet, then apply."""
    _refuse_out_of_scope(ports.signal, run_id, signal)
    outcome = signal_run(ports.signal, run_id, signal)
    if signal.kind == "cancel" and outcome.cancel_plan is not None:
        _apply_cancel(ports, run_id, outcome.cancel_plan)
    return outcome


def _refuse_out_of_scope(ports: SignalPorts, run_id: UUID, signal: Signal) -> None:
    """`validate` first, so a genuine AD-13 mismatch keeps its own refusal text; only a
    signal validation admits, and this epic has not built, is refused here instead."""
    writers = ports.writers
    run = require_run(writers, run_id)
    rows = writers.steps.list_for_run(run_id)
    park_row = row_at(rows, run.park_path)
    validate(run, park_row, signal)
    if not _in_scope(signal.kind, run.park_kind):
        raise Conflict(NOT_AVAILABLE.format(kind=signal.kind))


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
