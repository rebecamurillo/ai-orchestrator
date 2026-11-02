"""The trees a consult must leave untouched (AD-22): the offer's clean snapshot, and the
files that differ from it once the senior has exited.

**The snapshot is taken of clean trees.** The offer first sweeps both trees into a WIP
commit: porcelain status cannot see a further edit to a file the agent left modified, so
"HEAD and status unchanged" is exact only when nothing was modified to begin with. It is
stored on the consult entry at the offer, so a consult re-run after a crash is compared with
what the agent left, not with what the dead senior changed.

Files are named in AD-17's one spelling: run-worktree relative, a `workdir` path prefixed
`{workdir}/` (`agent_workdir.py`).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from orchestrator.application.rules.protected_paths import uncommitted
from orchestrator.application.steps import agent_workdir
from orchestrator.application.steps.context import StepContext, require_cwd, resolved_text
from orchestrator.application.templates.agent_row import STORY_ID_KEY
from orchestrator.domain.ports.git import Git

WIP_MESSAGE = "wip: story {id} attempt {n} (consult)"

#: The snapshot's two halves: the dispatch tree, and the worktree root on a `workdir` row.
TREE = "tree"
ROOT = "root"
HEAD = "head"
STATUS = "status"

#: What is named when HEAD moved but no file differs, or when there is nothing to compare.
MOVED_HEAD = "HEAD"
NO_SNAPSHOT = "no snapshot"


def sweep_and_snapshot(ctx: StepContext, n: int) -> dict[str, Any]:
    """Commit both trees under the consult's WIP message, then record them; raises
    `GitError` for the caller to park on."""
    story_id = resolved_text(ctx.with_resolved, STORY_ID_KEY)
    message = WIP_MESSAGE.format(id=story_id, n=n)
    return snapshot_trees(ctx.ports.git, require_cwd(ctx), agent_workdir.declared(ctx), message)


def snapshot_trees(git: Git, root: Path, workdir: str, message: str) -> dict[str, Any]:
    """`sweep_and_snapshot` for a caller holding no `StepContext` (the `verify_failed` offer,
    made by `apply_step_result`): the run worktree `root`, the normalised `workdir` or `""`."""
    agent_workdir.sweep_trees(git, root, workdir, message)
    halves = {TREE: root / workdir, ROOT: root} if workdir else {TREE: root}
    return {half: {HEAD: git.head_sha(at), STATUS: git.status(at)} for half, at in halves.items()}


def changed(ctx: StepContext, snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    """Every file either tree changed since `snapshot`, sorted; `()` when neither did."""
    names: set[str] = set()
    for half, at, prefix in _trees(ctx):
        before = snapshot.get(half)
        if not isinstance(before, Mapping):
            return (NO_SNAPSHOT,)
        names.update(prefix + name for name in _differences(ctx, at, before))
    return tuple(sorted(names))


def _trees(ctx: StepContext) -> list[tuple[str, Path, str]]:
    """`(half, path, prefix)` per tree the row spans."""
    workdir = agent_workdir.declared(ctx)
    if not workdir:
        return [(TREE, require_cwd(ctx), "")]
    return [(TREE, agent_workdir.tree(ctx), f"{workdir}/"), (ROOT, require_cwd(ctx), "")]


def _state(ctx: StepContext, at: Path) -> dict[str, Any]:
    return {HEAD: ctx.ports.git.head_sha(at), STATUS: ctx.ports.git.status(at)}


def _differences(ctx: StepContext, at: Path, before: Mapping[str, Any]) -> set[str]:
    now = _state(ctx, at)
    names: set[str] = set()
    old_head, new_head = before.get(HEAD), now[HEAD]
    if old_head != new_head:
        moved = (
            ctx.ports.git.diff_changes(at, old_head, new_head)
            if isinstance(old_head, str) and isinstance(new_head, str)
            else ()
        )
        names.update(change.path for change in moved)
        if not moved:
            names.add(MOVED_HEAD)
    lines = set(str(before.get(STATUS, "")).splitlines()) ^ set(now[STATUS].splitlines())
    names.update(change.path for change in uncommitted("\n".join(sorted(lines))))
    return names
