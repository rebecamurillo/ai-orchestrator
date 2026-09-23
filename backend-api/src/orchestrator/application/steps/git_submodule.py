"""The `git.submodule` kind: a hub Run's member repositories, as working folders (AD-9,
AD-14 — ratified 2026-09-23, hub-Run initiative workflow).

One kind with two forms, told apart by the keys the row's `with` carries, exactly as the
spine's DSL table states them:

- **bare, or `{update: true}`** → init + update of the Run worktree's submodules. The row is
  `done` with the workdirs it materialised, which is how the Operator reads off one row which
  member repositories this Run is about to work in. A worktree with no submodules is `done`
  too: there is nothing to initialize, and that is an answer rather than a stop.
- **`{workdir, branch, base?}`** → create-or-checkout of `branch` inside the submodule at
  `workdir`, upstream set, cut from `origin/{branch}` when that member's remote holds it,
  from `base` when it holds that, and from the submodule's current HEAD otherwise. The row is
  `done` with the sha the submodule's HEAD reached, the way `git.commit`'s is.

**The forms are exclusive, and neither is guessed.** The validator rejects a `with` carrying
the keys of both, or a `workdir` with no `branch` (spine "Template DSL v1 keys"). This
executor re-asks the same question because a row reaches it carrying `with_resolved` — values
the planner substituted (AD-7), not the text a validator read — and a step whose form cannot
be decided must park with a sentence the Operator can act on, never fall back to the other
form. That is the same rule AD-9 states for `workdir`: "never a silent fall back to the root".

**The branch is taken by its exact name.** AD-7 exempts a `git.submodule` branch from
allocation: it lives in the submodule's own repository, which the Run's allocator — which
asks the Run's origin — cannot reason about, so the name is resolved against the member's
remote when this row executes and never at plan time.

**Everything goes through the `Git` port's credential path** (AD-5), because a member
repository may be private. That is why this is a step kind at all and never a template
`shell` command: a `shell` row never receives `GITHUB_TOKEN`.

Nothing here writes a status or a Run column. A submodule is a working folder inside a
worktree, never a second workspace (AD-14), so `run.worktrees[]` is untouched.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.steps import (
    SUBMODULE_BASE_KEY,
    SUBMODULE_BRANCH_KEY,
    SUBMODULE_KIND,
    SUBMODULE_UPDATE_KEY,
    SUBMODULE_WORKDIR_KEY,
)
from orchestrator.application.steps.context import (
    StepContext,
    require_cwd,
    resolved_text,
)
from orchestrator.application.steps.registry import register
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.values import Park, StepResult

#: The kind this module implements and the four `with` keys its forms are made of, read back
#: from `KIND_META`'s own table rather than spelled a second time here — the validator judges
#: the shape those keys make, so they are named once (AD-9; `git_worktree.py` reads `mode`
#: back the same way). `UPDATE_KEY` is the update form's only key and is optional, a bare
#: `with` being the same row; the other three are the checkout form's, of which `BASE_KEY`
#: alone may be left out.
KIND = SUBMODULE_KIND
UPDATE_KEY = SUBMODULE_UPDATE_KEY
WORKDIR_KEY = SUBMODULE_WORKDIR_KEY
BRANCH_KEY = SUBMODULE_BRANCH_KEY
BASE_KEY = SUBMODULE_BASE_KEY

#: What the update form ends `done` with: the workdirs the Run can now run a step in.
INITIALIZED = "initialized {paths}"
NOTHING_TO_INITIALIZE = "no submodules"

#: How the paths are joined into that reason — a list a person reads, not a data format.
SEPARATOR = ", "

#: AD-9's own sentence for a `workdir` that is not a workdir. The same words the `agent`,
#: `git.commit` and `git.push` kinds park with, because it is the same stop.
NOT_A_SUBMODULE = "workdir {path} is not an initialized submodule"

#: What a row whose form cannot be decided parks with. Both are validation errors as well
#: (spine "Template DSL v1 keys"); this executor is the backstop for a resolved row.
AMBIGUOUS_FORM = "git.submodule takes update, or workdir and branch — never both"
NO_BRANCH = "git.submodule declares a workdir with no branch"

#: What a failing git command parks with. The reason names which form failed; git's own
#: message travels in `output_ref`, already redacted by the adapter (AD-5).
UPDATE_FAILED = "submodule update failed"
CHECKOUT_FAILED = "submodule checkout failed: {path}"


class GitSubmoduleExecutor:
    """Materialise the worktree's submodules, or put one of them on a branch."""

    def execute(self, ctx: StepContext) -> StepResult:
        worktree = require_cwd(ctx)
        workdir = resolved_text(ctx.with_resolved, WORKDIR_KEY)
        branch = resolved_text(ctx.with_resolved, BRANCH_KEY)
        base = resolved_text(ctx.with_resolved, BASE_KEY)
        declared_update = UPDATE_KEY in ctx.with_resolved
        if declared_update and (workdir or branch or base):
            return _park(ctx, AMBIGUOUS_FORM)
        if workdir and not branch:
            return _park(ctx, NO_BRANCH)
        if branch or base:
            if not workdir:
                return _park(ctx, AMBIGUOUS_FORM)
            return _checkout(ctx, worktree, workdir, branch, base or None)
        return _update(ctx, worktree)


def _update(ctx: StepContext, worktree: Path) -> StepResult:
    """Init + update every submodule, and report the workdirs that answered."""
    try:
        paths = ctx.ports.git.submodule_update(worktree)
    except GitError as error:
        return _park(ctx, UPDATE_FAILED, output=error.output)
    if not paths:
        return StepResult(status="done", gate=ctx.row.gate, reason=NOTHING_TO_INITIALIZE)
    return StepResult(
        status="done", gate=ctx.row.gate, reason=INITIALIZED.format(paths=SEPARATOR.join(paths))
    )


def _checkout(
    ctx: StepContext, worktree: Path, workdir: str, branch: str, base: str | None
) -> StepResult:
    """Create or check out the branch inside one submodule, and report its HEAD.

    `None` from the port is the one absence that has a sentence of its own: the path is not
    an initialized submodule, so nothing was written and the Operator's stop is a
    configuration fact rather than a git failure (AD-9).
    """
    try:
        sha = ctx.ports.git.submodule_checkout(worktree, workdir, branch, base)
    except GitError as error:
        return _park(ctx, CHECKOUT_FAILED.format(path=workdir), output=error.output)
    if sha is None:
        return _park(ctx, NOT_A_SUBMODULE.format(path=workdir))
    return StepResult(status="done", gate=ctx.row.gate, output_ref=sha)


def _park(ctx: StepContext, reason: str, *, output: str | None = None) -> StepResult:
    """The row errors and the Run stops on a state a person has to change (AD-13)."""
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        output_ref=output,
        reason=reason,
        park=Park(kind="misconfigured", reason=reason, path=ctx.row.path),
    )


register(KIND, GitSubmoduleExecutor())
