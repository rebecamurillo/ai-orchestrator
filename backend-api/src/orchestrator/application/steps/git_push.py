"""The `git.push` kind: this Run's branch onto the origin, and the two things it refuses
(FR-11, AD-13, AD-14).

**The default branch is refused before anything runs.** AD-14 says `git.push` refuses
`branch == repository.default_branch`, and the refusal is first on purpose: it is a fact
about the Template and the Repository, not about the remote, so no command needs to be sent
to discover it. That is also what makes the acceptance criterion checkable — "no push command
runs" is a property of a call log.

**A rejection is a park, never a force.** `push_rejected` is AD-13's own park kind and it
admits `retry`; `--force` would turn "someone else moved this branch" into "someone else's
work is gone". The remote's own words travel in `output_ref`, already redacted by the adapter
(AD-5).

**A `retry` syncs first.** AD-13's retry row says so in as many words: on a `push_rejected`
row a `Git.sync` runs before the push. This executor reads `ctx.resume_signal` — the gate
record `signal_run` wrote and committed — rather than a message the engine carried, which is
AD-9's rule for every worktree effect of a signal. A sync that itself cannot fast-forward
parks the same `push_rejected` the sync kind does: the branch diverged, and this row cannot
decide that either.

**`-u` only when this Run created the branch.** `run.worktrees[]` recorded that at
`git.worktree` time; nothing here re-decides it. Success sets `pushed: true` on that entry
through `RunUpdates`, which is what `cancel` reads to know a branch is no longer safe to
delete (AD-13).

**`with {workdir}`** (AD-14, ratified 2026-09-23, hub-Run initiative workflow) pushes the
submodule's own branch to the submodule's own origin, never the Run Repository's: the
default-branch refusal compares against `Git.submodule_default_branch`, not `env.
default_branch`, and `-u` is set unconditionally (`submodule_checkout` already wrote the
tracking config on the branch's first checkout, so a repeat is a harmless no-op — there is no
`run.worktrees[]`-shaped record of "did this Run push it before" for a submodule to read).
`run.worktrees[]` tracks the Run's own worktrees only, so a `workdir` push sets no `pushed`
flag anywhere (AD-14). **Owed to a follow-up:** `Git.sync` has no `workdir` form, so a
`retry` on a `workdir` push re-pushes without syncing first — AD-13's "a retry syncs first"
is not yet exact for this row.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from orchestrator.application.rules import protected_paths, push_anchors
from orchestrator.application.steps import (
    MERGE_KIND,
    PUSH_ALLOW_DEFAULT_KEY,
    PUSH_RETRY_KEY,
    WORKDIR_KEY,
    records,
)
from orchestrator.application.steps.agent_tail import PATH_SEPARATOR, PROTECTED
from orchestrator.application.steps.context import (
    StepContext,
    require_cwd,
    require_env,
    resolved_text,
)
from orchestrator.application.steps.git_merge import FROM_KEY
from orchestrator.application.steps.git_sync import DIVERGED
from orchestrator.application.steps.registry import register
from orchestrator.application.steps.step_log import logged
from orchestrator.domain.entities.run_records import ROOT_PATH
from orchestrator.domain.ports.git import Git, GitError
from orchestrator.domain.values import Park, RunUpdates, StepResult, Worktree

#: The kind this module implements (AD-9: named here, beside the executor, or nowhere).
KIND = "git.push"

#: The `with` keys `KIND_META` admits on this kind — the branch to push, and the submodule a
#: `workdir` row pushes instead of the worktree root (H2).
BRANCH_KEY = "branch"

#: The signal that makes this row sync before it pushes (AD-13).
RETRY = "retry"

#: The three refusals, each read by the acceptance criterion that names it. `DIVERGED` is
#: `git.sync`'s own sentence, imported rather than repeated: the retry's fetch and the sync
#: row's find the same fact, and an Operator reads the same words whichever row found it.
DEFAULT_BRANCH = "push refused: {branch} is the default branch"
REJECTED = "push rejected"
RETRY_LANDED = "pushed after {k} sync"
SYNC_FAILED = "sync before retry failed"

#: AD-9's own sentence for a `workdir` that is not a workdir — the same words `git.submodule`
#: and `git.commit` park with, because it is the same stop.
NOT_A_SUBMODULE = "workdir {path} is not an initialized submodule"


class GitPushExecutor:
    """Refuse the default branch, sync on a retry, push, and record that it landed."""

    def execute(self, ctx: StepContext) -> StepResult:
        return logged(ctx, lambda inner, _recorder: _push(inner))


def _push(ctx: StepContext) -> StepResult:
    env = require_env(ctx)
    worktree = require_cwd(ctx)
    branch = str(ctx.with_resolved[BRANCH_KEY])
    workdir = resolved_text(ctx.with_resolved, WORKDIR_KEY)
    git = ctx.ports.git
    if workdir:
        return _execute_workdir(ctx, git, worktree, branch, workdir)
    recorded = env.worktree_at(ctx.cwd)
    created = recorded is not None and recorded.created_branch
    attached = recorded is not None and not recorded.created_branch
    allowed = ctx.with_resolved.get(PUSH_ALLOW_DEFAULT_KEY) is True and attached
    if branch == env.default_branch and not allowed:
        return _park(ctx, DEFAULT_BRANCH.format(branch=branch), output=None)
    if ctx.resume_signal is not None and ctx.resume_signal.event == RETRY:
        try:
            git.sync(worktree, branch)
        except GitError as error:
            return _park(ctx, DIVERGED, output=error.output)
    if branch == env.default_branch and push_anchors.initiative_run(env.run):
        stopped = _anchor_check(ctx, git, worktree, branch)
        if stopped is not None:
            return stopped
    outcome = _push_declared(ctx, git, worktree, branch, created)
    if isinstance(outcome, StepResult):
        return outcome
    output, landed_after = outcome
    records.note_pushed(ctx, ROOT_PATH, worktree)
    return StepResult(
        status="done",
        gate=ctx.row.gate,
        output_ref=output,
        reason=RETRY_LANDED.format(k=landed_after) if landed_after else None,
        run_updates=_pushed(ctx, env.worktrees),
    )


def _push_declared(
    ctx: StepContext, git: Git, worktree: Path, branch: str, created: bool
) -> StepResult | tuple[str | None, int]:
    """Push, and on a rejection sync and push again up to the row's declared `retry.max`.

    Returns the push output and how many syncs it took, or the park that ended the row.
    """
    declared = ctx.with_resolved.get(PUSH_RETRY_KEY)
    allowed = int(declared["max"]) if isinstance(declared, dict) else 0
    syncs = 0
    while True:
        try:
            return git.push(worktree, branch, created), syncs
        except GitError as error:
            if syncs == allowed:
                return _park(ctx, REJECTED, output=error.output)
        syncs += 1
        try:
            git.sync(worktree, branch)
        except GitError as failure:
            return _park(ctx, SYNC_FAILED, output=failure.output)


def _anchor_check(ctx: StepContext, git: Git, worktree: Path, branch: str) -> StepResult | None:
    """`push_anchors` over the range the push brings to the default branch, or `None` to push."""
    env = require_env(ctx)
    source = _merge_source(ctx)
    if source is None:
        reason = push_anchors.NO_MERGE_SOURCE
        return StepResult(
            status="blocked",
            gate=ctx.row.gate,
            reason=reason,
            park=Park(kind="blocked", reason=reason, path=ctx.row.path),
        )
    changes = git.diff_changes(worktree, f"origin/{branch}", "HEAD")
    checked = push_anchors.checked(changes, env.test_globs)
    if not checked:
        return None
    # `read_file` tries `origin/{ref}` first, so HEAD is read at its SHA.
    head = git.head_sha(worktree)
    ours = {c.path: git.read_file(worktree, head, c.path) if head else None for c in checked}
    theirs = {c.path: git.read_file(worktree, source, c.path) for c in checked}
    hits = push_anchors.hits(checked, ours, theirs, env.accepted_paths)
    if not hits:
        return None
    reason = PROTECTED.format(paths=PATH_SEPARATOR.join(hit.path for hit in hits))
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        reason=reason,
        park=Park(kind="protected_path", reason=reason, path=ctx.row.path),
        payload=protected_paths.hits_payload(hits),
    )


def _merge_source(ctx: StepContext) -> str | None:
    """The `from` of the last `git.merge` row before this one, in plan order."""
    merges = [
        row
        for row in require_env(ctx).plan_rows
        if row.kind == MERGE_KIND and row.seq < ctx.row.seq
    ]
    if not merges:
        return None
    source = max(merges, key=lambda row: row.seq).with_resolved.get(FROM_KEY)
    return str(source) if source else None


def _execute_workdir(
    ctx: StepContext, git: Git, worktree: Path, branch: str, workdir: str
) -> StepResult:
    """The `workdir` half (AD-14): the submodule's own default branch and its own origin."""
    default = git.submodule_default_branch(worktree, workdir)
    if default is not None and branch == default:
        return _park(ctx, DEFAULT_BRANCH.format(branch=branch), output=None)
    try:
        output = git.push(worktree, branch, True, workdir=workdir)
    except GitError as error:
        return _park(ctx, REJECTED, output=error.output)
    if output is None:
        reason = NOT_A_SUBMODULE.format(path=workdir)
        return StepResult(
            status="error",
            gate=ctx.row.gate,
            reason=reason,
            park=Park(kind="misconfigured", reason=reason, path=ctx.row.path),
        )
    normalised = str(PurePosixPath(workdir))
    records.note_member(ctx, normalised)
    records.note_pushed(ctx, normalised, worktree / normalised)
    return StepResult(status="done", gate=ctx.row.gate, output_ref=output)


def _park(ctx: StepContext, reason: str, *, output: str | None) -> StepResult:
    """Both refusals are one park kind: AD-13's `push_rejected`, which admits `retry`.

    A sync that could not fast-forward reaches here too, and it says so: the reason is the
    sync kind's own sentence, so an Operator reads the same words whichever row found it.
    """
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        output_ref=output,
        reason=reason,
        park=Park(kind="push_rejected", reason=reason, path=ctx.row.path),
    )


def _pushed(ctx: StepContext, worktrees: tuple[Worktree, ...]) -> RunUpdates:
    """`pushed: true` on the entry this Run is standing in, and nothing else touched."""
    return RunUpdates(
        worktrees=tuple(
            entry.model_copy(update={"pushed": True}) if entry.path == ctx.cwd else entry
            for entry in worktrees
        )
    )


register(KIND, GitPushExecutor())
