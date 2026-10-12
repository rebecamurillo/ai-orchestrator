"""The `git.merge` kind: one epic's branch into the branch this Run is standing on
(AD-9, AD-13, AD-14 — ratified 2026-09-23, multi-repository initiative dispatch).

Four outcomes, and each is a fact about the two branches rather than a degree of failure:

- **A merge that went through is `done` with the commit it made.** `--no-ff` in the adapter,
  so the integration branch records that this epic landed as a commit of its own, and the
  sha travels in `output_ref` the way `git.commit`'s does.
- **A ref the branch already holds is `done · already merged`.** Not a no-op to hide: it is
  the answer AD-13's amended `retry` row names in as many words, for the Operator who
  resolved the conflict themselves, committed and pushed. The row re-runs, finds the work
  contained, and says so.
- **A branch the origin does not hold is `done · no upstream · no-op`.** A fresh initiative
  branch has no origin ref until its first push, and a template that merges it before every
  Story would otherwise park a conflict that is not one. The words are `git.sync`'s own.
- **A conflict parks `merge_conflict`** with AD-13's own sentence, `merge conflict: {from}
  into {branch}`, and git's listing beside it. The conflicted merge stays in the worktree —
  it is what the Operator opens — and the stop admits `retry` and `cancel` only.

`retry` re-runs this row **whole**; there is no half-done state to resume from and no
`Git.sync` before it, which is `push_rejected`'s and `verify_failed`'s rule rather than this
kind's (AD-13). What makes re-running safe is inside the port: `Git.merge` aborts any merge
in progress first. So, like `git.sync`, this executor reads nothing off `ctx.resume_signal`.

`{branch}` in the reason is the branch the *worktree* is on, read back off `run.worktrees[]`
where `git.worktree` recorded it — never re-derived here, because a second opinion about
which branch a Run is standing on is a second, disagreeing answer (AD-14).

The git output travels in `output_ref` rather than in the reason: the reason is the sentence
AD-13 fixes, and the output is what the Operator reads next to it. It is already redacted by
the adapter (AD-5), so storing it verbatim cannot leak a credential.
"""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext, require_cwd, require_env
from orchestrator.application.steps.git_sync import NO_UPSTREAM as NO_UPSTREAM_REASON
from orchestrator.application.steps.registry import register
from orchestrator.domain.ports.git import NO_UPSTREAM, GitError
from orchestrator.domain.values import Park, StepResult

#: The kind this module implements (AD-9: named here, beside the executor, or nowhere).
KIND = "git.merge"

#: The one `with` key `KIND_META` admits on this kind — and the placeholder AD-13's sentence
#: is written with, so the key and the words the Operator reads have one definition.
FROM_KEY = "from"

#: What a branch that already holds the ref ends `done` with (spine "Shipped kinds").
ALREADY_MERGED = "already merged"

#: The sentence AD-13 fixes for this park, verbatim.
CONFLICT = "merge conflict: {from} into {branch}"

#: What a Run whose worktree the environment does not know is reported as. `git.worktree`
#: records every worktree it opens, so this is a bug in that record rather than in a branch.
UNKNOWN_WORKTREE = "no recorded worktree for {path}"


class GitMergeExecutor:
    """Merge the declared branch into the one this Run's worktree is on."""

    def execute(self, ctx: StepContext) -> StepResult:
        env = require_env(ctx)
        worktree = require_cwd(ctx)
        recorded = env.worktree_at(ctx.cwd)
        if recorded is None:
            raise RuntimeError(UNKNOWN_WORKTREE.format(path=ctx.cwd))
        source = str(ctx.with_resolved[FROM_KEY])
        try:
            output = ctx.ports.git.merge(worktree, source)
        except GitError as error:
            reason = CONFLICT.format(**{FROM_KEY: source, "branch": recorded.branch})
            return StepResult(
                status="error",
                gate=ctx.row.gate,
                output_ref=error.output,
                reason=reason,
                park=Park(kind="merge_conflict", reason=reason, path=ctx.row.path),
            )
        if output is NO_UPSTREAM:
            return StepResult(status="done", gate=ctx.row.gate, reason=NO_UPSTREAM_REASON)
        if output is None:
            return StepResult(status="done", gate=ctx.row.gate, reason=ALREADY_MERGED)
        return StepResult(status="done", gate=ctx.row.gate, output_ref=output)


register(KIND, GitMergeExecutor())
