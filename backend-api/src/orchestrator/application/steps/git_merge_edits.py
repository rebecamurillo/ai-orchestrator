"""AD-17 over the merge agent's edits, before a `git.merge` row resumes (story 8.4).

Operator ruling, 2026-11-26: before a `continue` or `retry` resumes a merge the agent worked
on, a path is the agent's edit when its worktree content differs from both HEAD's and
MERGE_HEAD's version, or it is new in neither. Paths equal to MERGE_HEAD's version are what
the merged branch brings and are not hits. An edit to an anchor or an existing test file
parks `protected_path` with those hits, and the Operator's `continue` naming them lets them
stand through `run.accepted_paths`.

Unmerged paths are not read: their markers are git's, and a `continue` re-parks
`merge_conflict` on them. A `retry` that answers this module's own park re-runs whole, since
the Operator saw the hits and chose the abort.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from orchestrator.application.rules import protected_paths
from orchestrator.application.rules.merge_conflict import unmerged_paths
from orchestrator.application.steps.agent_tail import PATH_SEPARATOR, PROTECTED
from orchestrator.application.steps.context import StepContext, require_env
from orchestrator.domain.ports.git import Change
from orchestrator.domain.values import Park, StepResult

#: The refs the two sides of a merge in progress are read at.
OURS = "HEAD"
THEIRS = "MERGE_HEAD"

#: The first line of this park's `output_ref`, which is how a later `retry` knows it.
EDITS_HEADING = "merge agent edits:"

RESUMING = frozenset({"continue", "retry"})


def protected(ctx: StepContext, worktree: Path) -> StepResult | None:
    """The `protected_path` park the agent's edits call for, or `None` to resume."""
    signal = ctx.resume_signal
    if signal is None or signal.event not in RESUMING:
        return None
    if signal.event == "retry" and _answers_own_park(ctx):
        return None
    git = ctx.ports.git
    if not git.merge_in_progress(worktree):
        return None
    environment = require_env(ctx)
    edits = agent_edits(ctx, worktree)
    existing_tests = {
        edit.path
        for edit in edits
        if edit.kind != "added" and _is_test(edit.path, environment.test_globs)
    }
    hits = protected_paths.check_interactive(
        edits, environment.anchors | existing_tests, environment.accepted_paths, ()
    )
    if not hits:
        return None
    paths = [hit.path for hit in hits]
    reason = PROTECTED.format(paths=PATH_SEPARATOR.join(paths))
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        output_ref="\n".join((EDITS_HEADING, *paths)),
        reason=reason,
        park=Park(kind="protected_path", reason=reason, path=ctx.row.path),
        payload=protected_paths.hits_payload(hits),
    )


def agent_edits(ctx: StepContext, worktree: Path) -> tuple[Change, ...]:
    """What the worktree holds that neither side of the merge does."""
    git = ctx.ports.git
    status = git.status(worktree)
    unmerged = frozenset(unmerged_paths(status))
    untracked = protected_paths.untracked(status)
    edits: list[Change] = []
    for change in protected_paths.uncommitted(status):
        if change.path in unmerged:
            continue
        if change.path in untracked or all(
            git.diff(worktree, ref, change.path) for ref in (OURS, THEIRS)
        ):
            edits.append(change)
    return tuple(edits)


def _answers_own_park(ctx: StepContext) -> bool:
    previous = ctx.previous_attempt
    return previous is not None and (previous.output_ref or "").startswith(EDITS_HEADING)


def _is_test(path: str, globs: tuple[str, ...]) -> bool:
    return any(PurePosixPath(path).full_match(glob) for glob in globs)
