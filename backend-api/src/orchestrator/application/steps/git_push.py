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
"""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext, require_cwd, require_env
from orchestrator.application.steps.git_sync import DIVERGED
from orchestrator.application.steps.registry import register
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.values import Park, RunUpdates, StepResult, Worktree

#: The kind this module implements (AD-9: named here, beside the executor, or nowhere).
KIND = "git.push"

#: The one `with` key `KIND_META` admits on this kind.
BRANCH_KEY = "branch"

#: The signal that makes this row sync before it pushes (AD-13).
RETRY = "retry"

#: The three refusals, each read by the acceptance criterion that names it. `DIVERGED` is
#: `git.sync`'s own sentence, imported rather than repeated: the retry's fetch and the sync
#: row's find the same fact, and an Operator reads the same words whichever row found it.
DEFAULT_BRANCH = "push refused: {branch} is the default branch"
REJECTED = "push rejected"


class GitPushExecutor:
    """Refuse the default branch, sync on a retry, push, and record that it landed."""

    def execute(self, ctx: StepContext) -> StepResult:
        env = require_env(ctx)
        worktree = require_cwd(ctx)
        branch = str(ctx.with_resolved[BRANCH_KEY])
        if branch == env.default_branch:
            return _park(ctx, DEFAULT_BRANCH.format(branch=branch), output=None)
        recorded = env.worktree_at(ctx.cwd)
        created = recorded is not None and recorded.created_branch
        git = ctx.ports.git
        if ctx.resume_signal is not None and ctx.resume_signal.event == RETRY:
            try:
                git.sync(worktree, branch)
            except GitError as error:
                return _park(ctx, DIVERGED, output=error.output)
        try:
            output = git.push(worktree, branch, created)
        except GitError as error:
            return _park(ctx, REJECTED, output=error.output)
        return StepResult(
            status="done",
            gate=ctx.row.gate,
            output_ref=output,
            run_updates=_pushed(ctx, env.worktrees),
        )


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
