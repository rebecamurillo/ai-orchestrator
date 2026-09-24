"""The `git.commit` kind: the commit-guard (FR-10, FR-16, AD-17's second call site).

**The spec folder is staged first, and then everything else.** Two calls rather than one, and
the order is the rule: the Run's own spec folder is what an Operator's inline edit and the
agent's story file live in, and staging it by name first means a later `add -A` cannot be the
only reason it was included. A Run with no spec folder — `repo-init@1` declares none — stages
everything and nothing is missing. `Git.stage`'s own "everything" call excludes every gitlink
the tree records (AD-14, ratified 2026-09-23), so this row never commits a submodule pointer
move — a fact of the adapter, not of this module, and unconditional whether or not `workdir`
is declared.

**Nothing staged is `done`, not a failure.** A verify row that changed nothing, a Story the
agent finished without a file change, a `skip_story` whose frame wrote nothing: all of them
reach this row, and a Run that failed because there was nothing to commit would be a Run that
failed for succeeding. `git status --porcelain` decides it, after the staging, so an untracked
file counts — but it asks with `ignore_submodules=True`, the same flag `git.worktree`'s dirty
check reads by (AD-14, H7, 2026-09-24): staging excludes every gitlink the tree records, so a
hub Run whose only outstanding change is a member advanced onto its own branch has nothing
staged, and the status read has to agree or this row sees a "change" that `git commit` then
refuses as empty.

**A git failure here is `error`, never an unhandled exception.** Staging, reading status and
writing the commit can each fail — a lock file, a hook, a disk gone full — and the row parks
`misconfigured` with git's own (redacted) output next to it, the same shape `git.submodule`,
`git.push`, `git.sync` and `git.merge` park with. Letting one through would reach the
executor registry's own catch-all instead, which reports only the exception's class name and
sends the Operator to `docker compose logs` for the reason it already had.

**The protected-path check happens before the commit and never after it.** AD-17 puts it
here, over the union of the frame's agent ranges and the uncommitted tree, and a hit is
`error` + park `protected_path` with the files named. The rule itself is Epic 5's
(`domain/ports/protected_paths.py` says why an unwired port is not a green check); what is
here is the call and the routing, so Epic 5 changes a wiring line and not this module.

**The message is the row's, already resolved.** `signal_run` re-resolves it on this row after
`skip_story` (AD-13), so what `with_resolved["message"]` holds at execution time is what the
Operator's last decision left there. This module never composes one.

**`with {workdir}`** (AD-9, ratified 2026-09-23, hub-Run initiative workflow) runs the whole
row inside that submodule's own repository instead: `Git.commit(..., workdir=workdir)` stages
and commits there in one call, because a submodule's own tree has no spec folder to stage
first and no separate staging call to make ahead of it. `None` back from the port is `workdir`
not an initialized submodule — parked `misconfigured`, AD-9's own sentence, never a silent
fall back to the worktree root.

**The check runs in the submodule's tree too** (H2's IOU, paid by H4). AD-17's amendment puts
a `workdir` attempt's `start_sha`/`end_sha` inside that submodule's repository, so the frame's
agent ranges are diffed there — `rules/protected_paths.py::FrameAnchors` carries the row's own
`workdir` and does it — and what this row adds to them is the submodule's *uncommitted* tree
rather than the worktree root's. Every path either half reports is spelled `{workdir}/…`, the
one spelling `steps/agent_workdir.py` fixes for a hub Run, so the anchor set, `accepted_paths`
and the reason sentence are the same objects the root branch uses. One ordering difference
follows from the two trees: the root branch answers `no changes` before checking, because
nothing staged means nothing to judge, while a `workdir` row checks first — a clean submodule
tree says nothing about what an earlier attempt of the frame already committed inside it.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from orchestrator.application.rules import protected_paths
from orchestrator.application.steps import WORKDIR_KEY
from orchestrator.application.steps.context import (
    StepContext,
    require_cwd,
    require_env,
    resolved_text,
)
from orchestrator.application.steps.registry import register
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.values import Park, StepResult

#: The kind this module implements (AD-9: named here, beside the executor, or nowhere).
KIND = "git.commit"

#: The `with` keys `KIND_META` admits on this kind — the message `signal_run` rewrites, and
#: the submodule a `workdir` row commits in instead of the worktree root (H2).
MESSAGE_KEY = "message"

#: What a row with nothing to commit ends `done` with.
NO_CHANGES = "no changes"

#: What a protected-path hit parks the Run with, naming the files (AD-17).
PROTECTED = "protected paths: {paths}"

#: How the hit list is written into the reason.
PATH_SEPARATOR = ", "

#: AD-9's own sentence for a `workdir` that is not a workdir — the same words `git.submodule`
#: and `git.push` park with, because it is the same stop.
NOT_A_SUBMODULE = "workdir {path} is not an initialized submodule"

#: What a staging, status or commit command that failed for a git reason parks with. The
#: command's own (redacted) output travels in `output_ref`, the same split every other git
#: kind's park uses.
COMMIT_FAILED = "commit failed"

#: What `git status --porcelain` separates its entries with, and how a changed path is read
#: out of one: `XY path`, three characters of status and then the name.
STATUS_PREFIX = 3


class GitCommitExecutor:
    """Stage the spec folder, then everything; refuse a protected path; commit the rest."""

    def execute(self, ctx: StepContext) -> StepResult:
        env = require_env(ctx)
        worktree = require_cwd(ctx)
        git = ctx.ports.git
        message = str(ctx.with_resolved[MESSAGE_KEY])
        workdir = resolved_text(ctx.with_resolved, WORKDIR_KEY)
        if workdir:
            return _in_workdir(ctx, workdir, message)
        try:
            if env.spec_folder:
                git.stage(worktree, env.spec_folder)
            git.stage(worktree)
            status = git.status(worktree, ignore_submodules=True)
        except GitError as error:
            return _park(ctx, COMMIT_FAILED, output=error.output)
        changed = _changed(status)
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
        try:
            sha = git.commit(worktree, message)
        except GitError as error:
            return _park(ctx, COMMIT_FAILED, output=error.output)
        return StepResult(status="done", gate=ctx.row.gate, output_ref=sha)


def _in_workdir(ctx: StepContext, workdir: str, message: str) -> StepResult:
    """The `workdir` branch: check the submodule's own scope, then commit inside it (H2, H4).

    The row's `workdir` is normalised once here, so `./repos/member` and `repos/member/` name
    one prefix; the port normalises the same value again when it resolves the folder, which is
    what keeps a Template's spelling from reaching either answer.
    """
    git = ctx.ports.git
    worktree, normalised = require_cwd(ctx), str(PurePosixPath(workdir))
    try:
        status = git.status(worktree / normalised)
    except GitError as error:
        return _park(ctx, COMMIT_FAILED, output=error.output)
    staged = tuple(f"{normalised}/{path}" for path in _changed(status))
    hits = _protected(ctx, staged, require_env(ctx).accepted_paths)
    if hits:
        reason = PROTECTED.format(paths=PATH_SEPARATOR.join(hits))
        return StepResult(
            status="error",
            gate=ctx.row.gate,
            reason=reason,
            park=Park(kind="protected_path", reason=reason, path=ctx.row.path),
            payload=protected_paths.hits_payload(hits),
        )
    try:
        sha = git.commit(worktree, message, workdir=workdir)
    except GitError as error:
        return _park(ctx, COMMIT_FAILED, output=error.output)
    if sha is None:
        reason = NOT_A_SUBMODULE.format(path=workdir)
        return StepResult(
            status="error",
            gate=ctx.row.gate,
            reason=reason,
            park=Park(kind="misconfigured", reason=reason, path=ctx.row.path),
        )
    return StepResult(status="done", gate=ctx.row.gate, output_ref=sha)


def _park(ctx: StepContext, reason: str, *, output: str | None) -> StepResult:
    """A staging, status or commit command that failed for a git reason — the same shape
    `git.submodule`, `git.push`, `git.sync` and `git.merge` park with, so this row never
    leaves an unhandled `GitError` for the executor registry's own catch-all to report as
    the exception's class name alone."""
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        output_ref=output,
        reason=reason,
        park=Park(kind="misconfigured", reason=reason, path=ctx.row.path),
    )


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
