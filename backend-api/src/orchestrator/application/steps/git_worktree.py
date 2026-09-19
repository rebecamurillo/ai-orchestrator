"""The `git.worktree` kind: the worktree a Run works in, and the install that follows it
(AD-14, FR-9).

Four things happen here, in this order, and each of them is a rule rather than a step of a
recipe:

**The base clone is ensured, never assumed.** `/work/{project}/{repo}/base` may not exist —
a Repository registered but never checked — and it may be stale. `base_exists` decides
between a clone and a fetch without either one touching the filesystem itself (AD-14).

**A worktree that is already there is reused when it is clean and refused when it is not.**
AD-14 says so in as many words. The refusal is `misconfigured`, because a dirty worktree is
a state of the machine an Operator has to look at, and re-creating it would throw away work
nobody looked at.

**Whether this Run created the branch is decided once, here.** `branch_exists(origin/{branch})`
answers it: an existing branch is checked out and tracks its origin, an absent one is created
from `origin/{base}`. `git.push` reads the answer back off `run.worktrees[]` to decide `-u`,
and `cancel` reads it to decide whether deleting the branch is safe (AD-13) — so a second
opinion later would be a second, disagreeing answer.

**`install_command` runs inside `git.worktree`, not as a row of its own** (AD-14, spine
"Shipped kinds"): `epic@1` has no install step, and a Repository that declares no command has
nothing to run rather than an empty row to explain. Its output goes to the row's own log,
because it is this row's output.

The Run's own columns — `worktree_path`, `worktrees[]` — are returned as `RunUpdates` and
written by `apply_step_result` (AD-8). Nothing here writes a status or a Run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog

from orchestrator.application.steps.context import (
    RunEnvironment,
    StepContext,
    log_path,
    require_env,
    require_process,
    require_workspace,
)
from orchestrator.application.steps.registry import register
from orchestrator.application.templates.rows import TIMEOUT_KEY
from orchestrator.domain.statuses import ParkKind
from orchestrator.domain.values import Park, RunUpdates, StepResult, Worktree

log = structlog.get_logger(__name__)

#: The kind this module implements (AD-9: named here, beside the executor, or nowhere).
KIND = "git.worktree"

#: The two `with` keys `KIND_META` admits on this kind.
BASE_KEY = "base"
BRANCH_KEY = "branch"

#: `KIND_META["git.worktree"].timeout_default_min` — what an install gets when the row
#: carries no resolved timeout of its own.
DEFAULT_TIMEOUT_MIN = 5

#: The path a `Workspace` is asked about to learn whether its own root is there at all.
ROOT = "."

#: The reasons this row leaves, each read by the acceptance criterion that names it.
REUSED = "reused worktree"
NO_INSTALL = "no install_command"
DIRTY = "worktree dirty: {path}"
INSTALL_FAILED = "install failed: exit {code}"
INSTALL_TIMED_OUT = "timeout {path} after {n} min"
#: AD-14 backstop: another Run holds the same (repository, branch) partition (story 5-1).
HELD_BY = "branch held by {run}"


@dataclass(frozen=True)
class _Opened:
    """What opening the worktree settled: who created the branch, and what to say about it."""

    created_branch: bool
    #: `REUSED` when the worktree was already there, `None` when this row made it.
    reason: str | None


class GitWorktreeExecutor:
    """Ensure the base clone, then the worktree, then run the Repository's install."""

    def execute(self, ctx: StepContext) -> StepResult:
        env = require_env(ctx)
        # AD-14 backstop: a race between pre-flight passing and this row executing may have
        # put another Run on the same (repository, branch) partition (story 5-1). Refuse
        # rather than clobbering the other Run's worktree.
        if env.held_by_label is not None:
            reason = HELD_BY.format(run=env.held_by_label)
            return StepResult(
                status="error",
                gate=ctx.row.gate,
                reason=reason,
                park=Park(kind="misconfigured", reason=reason, path=ctx.row.path),
            )
        branch = str(ctx.with_resolved[BRANCH_KEY])
        base = str(ctx.with_resolved[BASE_KEY])
        worktree = env.worktree_dir(ctx.ports.work_dir, branch)
        _ensure_base(ctx, env, base)
        opened = _open_worktree(ctx, env, branch=branch, base=base)
        if isinstance(opened, StepResult):
            return opened
        updates = _run_updates(env, worktree, branch, created_branch=opened.created_branch)
        return _install(ctx, env, worktree, updates, opened.reason)


def _ensure_base(ctx: StepContext, env: RunEnvironment, base: str) -> None:
    """Clone the base when it is not there, and bring it up to date when it is (AD-14)."""
    git, base_dir = ctx.ports.git, env.base_dir(ctx.ports.work_dir)
    if git.base_exists(base_dir):
        git.fetch_base(base_dir, base)
    else:
        git.clone_base(env.repository_url, base_dir)


def _open_worktree(
    ctx: StepContext, env: RunEnvironment, *, branch: str, base: str
) -> _Opened | StepResult:
    """Reuse, refuse or create — answering `created_branch`, or the refusal itself."""
    git = ctx.ports.git
    base_dir = env.base_dir(ctx.ports.work_dir)
    worktree = env.worktree_dir(ctx.ports.work_dir, branch)
    if require_workspace(ctx, str(worktree)).exists(ROOT):
        if git.status(worktree).strip():
            reason = DIRTY.format(path=worktree)
            return StepResult(
                status="error",
                gate=ctx.row.gate,
                reason=reason,
                park=Park(kind="misconfigured", reason=reason, path=ctx.row.path),
            )
        log.info(REUSED, path=ctx.row.path, worktree=str(worktree))
        recorded = env.worktree_at(str(worktree))
        created = recorded.created_branch if recorded is not None else False
        return _Opened(created_branch=created, reason=REUSED)
    if git.branch_exists(base_dir, branch):
        git.worktree_add(base_dir, worktree, branch, None)
        return _Opened(created_branch=False, reason=None)
    git.worktree_add(base_dir, worktree, branch, f"origin/{base}")
    return _Opened(created_branch=True, reason=None)


def _run_updates(
    env: RunEnvironment, worktree: Path, branch: str, *, created_branch: bool
) -> RunUpdates:
    """`run.worktree_path`, and the entry appended to `run.worktrees[]` if absent (AD-14)."""
    path = str(worktree)
    entries = env.worktrees
    if env.worktree_at(path) is None:
        entries = (
            *entries,
            Worktree(branch=branch, path=path, created_branch=created_branch, pushed=False),
        )
    return RunUpdates(worktree_path=path, worktrees=entries)


def _install(
    ctx: StepContext,
    env: RunEnvironment,
    worktree: Path,
    updates: RunUpdates,
    opened: str | None,
) -> StepResult:
    """The Repository's `install_command` in the new worktree, or the reason there is none."""
    command = env.install_command.strip()
    if not command:
        log.info(NO_INSTALL, path=ctx.row.path)
        return StepResult(
            status="done", gate=ctx.row.gate, reason=opened or NO_INSTALL, run_updates=updates
        )
    timeout_min = ctx.with_resolved.get(TIMEOUT_KEY, DEFAULT_TIMEOUT_MIN)
    output = log_path(ctx)
    process = require_process(ctx)
    handle = process.start(command, cwd=worktree, env={}, timeout_min=timeout_min, log_path=output)
    outcome = process.wait(handle)
    if outcome.timed_out:
        reason = INSTALL_TIMED_OUT.format(path=ctx.row.path, n=timeout_min)
        return _failed(ctx, reason, output, "timeout", updates)
    if outcome.exit_code != 0:
        reason = INSTALL_FAILED.format(code=outcome.exit_code)
        return _failed(ctx, reason, output, "misconfigured", updates)
    return StepResult(
        status="done",
        gate=ctx.row.gate,
        output_ref=str(output),
        log_path=str(output),
        reason=opened,
        run_updates=updates,
    )


def _failed(
    ctx: StepContext, reason: str, output: Path, kind: ParkKind, updates: RunUpdates
) -> StepResult:
    """A failed install: the row errors and the Run stops on the log the Operator opens.

    The updates travel with the failure. The worktree exists whatever the install did, and
    `cancel` removes it and deletes the branch it created by reading `run.worktrees[]`
    (AD-13) — a park that forgot to record it would leave both behind.
    """
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        output_ref=str(output),
        log_path=str(output),
        reason=reason,
        park=Park(kind=kind, reason=reason, path=ctx.row.path),
        run_updates=updates,
    )


register(KIND, GitWorktreeExecutor())
