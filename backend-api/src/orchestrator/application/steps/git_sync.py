"""The `git.sync` kind: bring this Run's branch up to date, or say why there is nothing to
do (AD-14, FR-10).

Three outcomes, and each is a different fact about the branch rather than a different degree
of failure:

- **No upstream is a no-op, not an error.** A branch this Run created and has not pushed has
  none, and a Template with a Story loop syncs before every Story — so refusing here would
  park every first Story
  of every new epic branch. AD-14 states it: `Git.sync` is a recorded no-op when
  `rev-parse --abbrev-ref @{upstream}` fails. The port answers `None`, and the row is `done`
  with the reason the Operator reads.
- **A fast-forward is the whole of "sync".** No merge, no rebase, no `--force`: what this row
  does is take what the remote already has.
- **A history that will not fast-forward parks `push_rejected`** (AD-13 names that park for
  exactly this: "`push_rejected` also carries `sync: branch diverged`"). Someone else moved
  the branch, and resolving that is a person's decision, not this system's.

`retry` re-runs the row whole; there is no half-done state to resume from, which is why this
executor reads nothing off `ctx.resume_signal`.

The git output travels in `output_ref` rather than in the reason: the reason is the sentence
AD-13 fixes, and the output is what the Operator reads next to it. It is already redacted by
the adapter (AD-5), so storing it verbatim cannot leak a credential.
"""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext, require_cwd, require_env
from orchestrator.application.steps.registry import register
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.values import Park, StepResult

#: The kind this module implements (AD-9: named here, beside the executor, or nowhere).
KIND = "git.sync"

#: What a branch with no upstream records, and ends `done` with (AD-14).
NO_UPSTREAM = "no upstream · no-op"

#: What a history that will not fast-forward parks the Run with (AD-13).
DIVERGED = "sync: branch diverged"

#: What a Run whose worktree the environment does not know is reported as. `git.worktree`
#: records every worktree it opens, so this is a bug in that record rather than in the branch.
UNKNOWN_WORKTREE = "no recorded worktree for {path}"


class GitSyncExecutor:
    """Fetch and fast-forward the branch this Run's worktree is on."""

    def execute(self, ctx: StepContext) -> StepResult:
        env = require_env(ctx)
        worktree = require_cwd(ctx)
        recorded = env.worktree_at(ctx.cwd)
        if recorded is None:
            raise RuntimeError(UNKNOWN_WORKTREE.format(path=ctx.cwd))
        try:
            output = ctx.ports.git.sync(worktree, recorded.branch)
        except GitError as error:
            return StepResult(
                status="error",
                gate=ctx.row.gate,
                output_ref=error.output,
                reason=DIVERGED,
                park=Park(kind="push_rejected", reason=DIVERGED, path=ctx.row.path),
            )
        if output is None:
            return StepResult(status="done", gate=ctx.row.gate, reason=NO_UPSTREAM)
        return StepResult(status="done", gate=ctx.row.gate, output_ref=output)


register(KIND, GitSyncExecutor())
