"""The `git.worktree` kind: the worktree a Run works in, and nothing else (AD-14, FR-9).

Three things happen here, in this order, and each of them is a rule rather than a step of a
recipe:

**The base clone is ensured, never assumed.** `/work/{project}/{repo}/base` may not exist —
a Repository registered but never checked — and it may be stale. `base_exists` decides
between a clone and a fetch without either one touching the filesystem itself (AD-14).

**A worktree that is already there is reused when it is clean and refused when it is not.**
AD-14 says so in as many words. The refusal is `misconfigured`, because a dirty worktree is
a state of the machine an Operator has to look at, and re-creating it would throw away work
nobody looked at. **Submodule state is not part of the question** (AD-14, ratified
2026-09-24, H7): a hub Run advances each member onto the initiative branch and never commits
the gitlink move, so an advanced submodule is a permanent, intended divergence rather than
dirt, and the check asks `status(ignore_submodules=True)`.

**Whether this Run created the branch is decided once, here.** `branch_exists(origin/{branch})`
answers it: an existing branch is checked out and tracks its origin, an absent one is created
from `origin/{base}`. `git.push` reads the answer back off `run.worktrees[]` to decide `-u`,
and `cancel` reads it to decide whether deleting the branch is safe (AD-13) — so a second
opinion later would be a second, disagreeing answer.

**`mode: attach` changes exactly one thing: which branch is brought up to date first.** The
planner hands an attach row the branch by its exact name rather than a fresh ordinal of it
(AD-7, `templates/branches.py`), and AD-7 asks for that branch "at its origin head" — so the
base clone is fetched *for the declared branch* instead of for the row's `base`, and
everything after it is the ordinary path: the branch the origin holds is checked out, one it
does not is created at `origin/{base}`, a clean worktree is reused and a dirty one refused.
Sharing the branch across Runs is the point of the mode (AD-14 waives the fresh-branch
guarantee for these frames); AD-12's `{repository_id}:{branch}` partition is what keeps two
of them from writing it at once.

**No install runs here** (Operator decision, 2026-09-27, superseding the AD-14 sentence
that put it inside this kind): the Repository's `install_command` is a `setup` row the
template declares — `run: "{{repository.install_command}}"` — so what a Run executes is
readable off its template, and a Repository that declares no command plans that row
`skipped` rather than running an invisible nothing. The hidden run this replaces also ran
*in addition to* the declared `setup` rows the shipped templates already carried, so every
install executed twice.

The Run's own columns — `worktree_path`, `worktrees[]` — are returned as `RunUpdates` and
written by `apply_step_result` (AD-8). Nothing here writes a status or a Run.

**A git command that fails for a git reason is `error`, never an unhandled exception.** The
clone/fetch and the branch/worktree checks each run inside their own `try`, and a `GitError`
parks `misconfigured` with git's own (redacted) output — the same shape `git.commit`,
`git.submodule`, `git.push` and `git.sync` park with. Letting one through would reach the
executor registry's own catch-all instead, which reports only the exception's class name and
sends the Operator to `docker compose logs` for the reason it already had.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog

from orchestrator.application.steps import ATTACH_MODE, WORKTREE_MODE_KEY
from orchestrator.application.steps.context import (
    RunEnvironment,
    StepContext,
    require_env,
    require_workspace,
)
from orchestrator.application.steps.registry import register
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.values import Park, RunUpdates, StepResult, Worktree

log = structlog.get_logger(__name__)

#: The kind this module implements (AD-9: named here, beside the executor, or nowhere).
KIND = "git.worktree"

#: Two of the three `with` keys `KIND_META` admits on this kind. The third, `mode`, and its
#: one value come from the kind table itself rather than being spelled again here, because
#: the planner judges that same token (AD-9: a kind's vocabulary is named once or nowhere).
BASE_KEY = "base"
BRANCH_KEY = "branch"

#: The path a `Workspace` is asked about to learn whether its own root is there at all.
ROOT = "."

#: The reasons this row leaves, each read by the acceptance criterion that names it.
REUSED = "reused worktree"
DIRTY = "worktree dirty: {path}"
#: AD-14 backstop: another Run holds the same (repository, branch) partition (story 5-1).
HELD_BY = "branch held by {run}"
#: What a failed clone or fetch of the base parks with. Git's own (redacted) output travels
#: in `output_ref`, the same split every other git kind's park uses — a row never leaves an
#: unhandled `GitError` for the executor registry's own catch-all, which reports only the
#: exception's class name.
BASE_CLONE_FAILED = "base clone failed"
#: What a failed `branch_exists`, `worktree_add` or dirty-check `status` parks with.
WORKTREE_OPEN_FAILED = "worktree open failed"


@dataclass(frozen=True)
class _Opened:
    """What opening the worktree settled: who created the branch, and what to say about it."""

    created_branch: bool
    #: `REUSED` when the worktree was already there, `None` when this row made it.
    reason: str | None


class GitWorktreeExecutor:
    """Ensure the base clone, then the worktree — the install is the template's own row."""

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
        attached = ctx.with_resolved.get(WORKTREE_MODE_KEY) == ATTACH_MODE
        worktree = env.worktree_dir(ctx.ports.work_dir, branch)
        ensured = _ensure_base(ctx, env, branch if attached else base)
        if ensured is not None:
            return ensured
        opened = _open_worktree(ctx, env, branch=branch, base=base)
        if isinstance(opened, StepResult):
            return opened
        updates = _run_updates(env, worktree, branch, created_branch=opened.created_branch)
        return StepResult(
            status="done", gate=ctx.row.gate, reason=opened.reason, run_updates=updates
        )


def _ensure_base(ctx: StepContext, env: RunEnvironment, branch: str) -> StepResult | None:
    """Clone the base when it is not there, and bring it up to date when it is (AD-14).

    `branch` is the row's `base` on the ordinary path and the *declared* branch on the
    attach path — the branch the worktree is about to be put on, which AD-7 wants at its
    origin head. `fetch_base` brings every head up to date either way and then points the
    base clone's own `HEAD` at the one named, so naming the attach branch is what makes "at
    its origin head" a statement about this row rather than a coincidence of the refspec.

    A clone or fetch can fail for a git reason — a network blip, a revoked token, a server
    gone away — and that is `error` + park here, never an exception this function lets
    through: `None` back is "went fine", the same shape `_open_worktree` answers with.
    """
    git, base_dir = ctx.ports.git, env.base_dir(ctx.ports.work_dir)
    try:
        if git.base_exists(base_dir):
            git.fetch_base(base_dir, branch)
        else:
            git.clone_base(env.repository_url, base_dir)
    except GitError as error:
        return _git_failed(ctx, BASE_CLONE_FAILED, error.output)
    return None


def _open_worktree(
    ctx: StepContext, env: RunEnvironment, *, branch: str, base: str
) -> _Opened | StepResult:
    """Reuse, refuse or create — answering `created_branch`, or the refusal itself."""
    git = ctx.ports.git
    base_dir = env.base_dir(ctx.ports.work_dir)
    worktree = env.worktree_dir(ctx.ports.work_dir, branch)
    try:
        if require_workspace(ctx, str(worktree)).exists(ROOT):
            # Submodule state is not this worktree's own dirt (AD-14, H7 defect fix
            # 2026-09-24): `git.submodule` puts each member on the initiative branch and the
            # hub Run never commits the gitlink move, so the divergence is permanent and
            # intended. Counting it refused every second Run on the worktree, and every
            # retry after a park.
            if git.status(worktree, ignore_submodules=True).strip():
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
    except GitError as error:
        return _git_failed(ctx, WORKTREE_OPEN_FAILED, error.output)


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


def _git_failed(ctx: StepContext, reason: str, output: str | None) -> StepResult:
    """A base clone/fetch or a worktree open that failed for a git reason — the same shape
    `git.submodule`, `git.push`, `git.sync` and `git.commit` park with."""
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        output_ref=output,
        reason=reason,
        park=Park(kind="misconfigured", reason=reason, path=ctx.row.path),
    )


register(KIND, GitWorktreeExecutor())
