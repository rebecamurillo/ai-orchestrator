"""The `git.commit` kind: the commit-guard (FR-10, FR-16, AD-17's second call site).

**The spec folder is staged first, and then everything else.** Two calls rather than one, and
the order is the rule: the Run's own spec folder is what an Operator's inline edit and the
agent's story file live in, and staging it by name first means a later `add -A` cannot be the
only reason it was included. A Run with no spec folder — `repo-init@1` declares none — stages
everything and nothing is missing.

**Nothing staged is `done`, not a failure.** A verify row that changed nothing, a Story the
agent finished without a file change, a `skip_story` whose frame wrote nothing: all of them
reach this row, and a Run that failed because there was nothing to commit would be a Run that
failed for succeeding. `git status --porcelain` decides it, after the staging, so an untracked
file counts.

**The protected-path check happens before the commit and never after it.** AD-17 puts it
here, over the union of the frame's agent ranges and the uncommitted tree, and a hit is
`error` + park `protected_path` with the files named. The rule itself is Epic 5's
(`domain/ports/protected_paths.py` says why an unwired port is not a green check); what is
here is the call and the routing, so Epic 5 changes a wiring line and not this module.

**The message is the row's, already resolved.** `signal_run` re-resolves it on this row after
`skip_story` (AD-13), so what `with_resolved["message"]` holds at execution time is what the
Operator's last decision left there. This module never composes one.
"""

from __future__ import annotations

from orchestrator.application.rules import protected_paths
from orchestrator.application.steps.context import StepContext, require_cwd, require_env
from orchestrator.application.steps.registry import register
from orchestrator.domain.values import Park, StepResult

#: The kind this module implements (AD-9: named here, beside the executor, or nowhere).
KIND = "git.commit"

#: The one `with` key `KIND_META` admits on this kind — the message `signal_run` rewrites.
MESSAGE_KEY = "message"

#: What a row with nothing to commit ends `done` with.
NO_CHANGES = "no changes"

#: What a protected-path hit parks the Run with, naming the files (AD-17).
PROTECTED = "protected paths: {paths}"

#: How the hit list is written into the reason.
PATH_SEPARATOR = ", "

#: What `git status --porcelain` separates its entries with, and how a changed path is read
#: out of one: `XY path`, three characters of status and then the name.
STATUS_PREFIX = 3


class GitCommitExecutor:
    """Stage the spec folder, then everything; refuse a protected path; commit the rest."""

    def execute(self, ctx: StepContext) -> StepResult:
        env = require_env(ctx)
        worktree = require_cwd(ctx)
        git = ctx.ports.git
        if env.spec_folder:
            git.stage(worktree, env.spec_folder)
        git.stage(worktree)
        changed = _changed(git.status(worktree))
        if not changed:
            return StepResult(status="done", gate=ctx.row.gate, reason=NO_CHANGES)
        hits = _protected(ctx, changed, env.accepted_paths)
        if hits:
            reason = PROTECTED.format(paths=PATH_SEPARATOR.join(hits))
            return StepResult(
                status="error",
                gate=ctx.row.gate,
                reason=reason,
                park=Park(kind="protected_path", reason=reason, path=ctx.row.path),
                # The Accept (6.6) compares the Operator's `files` against the list the Run
                # reported, so this park has to record one too. Paths only: `ProtectedPaths.
                # check` answers no kinds and its member set is frozen (its own docstring).
                payload=protected_paths.hits_payload(hits),
            )
        sha = git.commit(worktree, str(ctx.with_resolved[MESSAGE_KEY]))
        return StepResult(status="done", gate=ctx.row.gate, output_ref=sha)


def _changed(status: str) -> tuple[str, ...]:
    """The paths `git status --porcelain` listed, without the two status characters."""
    return tuple(line[STATUS_PREFIX:].strip() for line in status.splitlines() if line.strip())


def _protected(
    ctx: StepContext, changed: tuple[str, ...], accepted: tuple[str, ...]
) -> tuple[str, ...]:
    """The frozen anchors among the staged paths — `()` while nothing implements the rule."""
    rule = ctx.ports.protected_paths
    if rule is None:
        return ()
    return rule.check(changed=changed, accepted=accepted)


register(KIND, GitCommitExecutor())
