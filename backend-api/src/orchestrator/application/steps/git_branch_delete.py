"""The `git.branch_delete` kind: delete the merged branch on origin and log what happened.

Refusals (blank names, the default branch, an adapter without `RemoteBranches`) ask no
operation and write no log. The rest is one logged operation (AD-40).

`step_log.logged` is not used: it swaps `ctx.ports.git` for a recorder, and a
`runtime_checkable` `isinstance` on Python 3.14 reads attributes statically, so the recorder
would never satisfy `RemoteBranches`.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.steps import BRANCH_DELETE_KIND, WORKDIR_KEY
from orchestrator.application.steps.context import (
    StepContext,
    require_cwd,
    require_env,
    resolved_text,
)
from orchestrator.application.steps.registry import register
from orchestrator.application.steps.step_log import INDENT, write_step_log
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.remote_branches import RemoteBranches
from orchestrator.domain.values import Park, StepResult

KIND = BRANCH_DELETE_KIND

BRANCH_KEY = "branch"
NEEDS_BRANCH = "branch_delete needs a branch and a known default branch"
IS_DEFAULT = "refuses to delete the default branch {branch}"
NO_PORT = "git adapter cannot delete a remote branch"
DELETED = "deleted origin/{branch}"
GONE = "already gone"
REJECTED = "branch delete rejected"
OPERATION = "git push origin --delete {branch}"


class GitBranchDeleteExecutor:
    """Delete `origin/{branch}`, never forced, never the default branch."""

    def execute(self, ctx: StepContext) -> StepResult:
        branch = resolved_text(ctx.with_resolved, BRANCH_KEY)
        default = require_env(ctx).default_branch
        if not branch or not default:
            return _park(ctx, "misconfigured", NEEDS_BRANCH)
        if _names_default(branch, default):
            return _park(ctx, "misconfigured", IS_DEFAULT.format(branch=branch))
        git = ctx.ports.git
        if not isinstance(git, RemoteBranches):
            return _park(ctx, "misconfigured", NO_PORT)
        cwd = require_cwd(ctx)
        workdir = resolved_text(ctx.with_resolved, WORKDIR_KEY)
        if workdir:
            cwd = cwd / workdir
        return _delete(ctx, git, cwd, branch)


def _names_default(branch: str, default: str) -> bool:
    """git resolves a delete's destination by suffix, so `heads/main` and `refs/heads/main`
    both name `main` on the remote and must be refused like `main`."""
    full = f"refs/heads/{default}"
    return branch == full or full.endswith(f"/{branch}")


def _delete(ctx: StepContext, git: RemoteBranches, cwd: Path, branch: str) -> StepResult:
    operation = OPERATION.format(branch=branch)
    try:
        held = git.delete_remote_branch(cwd, branch)
    except GitError as error:
        lines = [operation, *(f"{INDENT}{line}" for line in error.output.splitlines())]
        return _park(
            ctx, "push_rejected", REJECTED, output=error.output, log=write_step_log(ctx, lines)
        )
    reason = DELETED.format(branch=branch) if held else GONE
    log = write_step_log(ctx, [operation, f"{INDENT}{'deleted' if held else GONE}"])
    return StepResult(status="done", gate=ctx.row.gate, reason=reason, log_path=log)


def _park(
    ctx: StepContext,
    kind: str,
    reason: str,
    *,
    output: str | None = None,
    log: str | None = None,
) -> StepResult:
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        output_ref=output,
        reason=reason,
        log_path=log,
        park=Park(kind=kind, reason=reason, path=ctx.row.path),  # type: ignore[arg-type]
    )


register(KIND, GitBranchDeleteExecutor())
