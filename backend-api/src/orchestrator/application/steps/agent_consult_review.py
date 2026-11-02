"""What a `blocked` consult reviews a test-edit approval against (AD-17's and AD-22's
2026-11-02 amendments, hard rule 1).

**Before the senior is dispatched** (`prepare`), the consult attempt kills the blocked
agent's process group, so nothing it left running writes afterwards, then clears its own
decision path and the story baseline beside it: `.orchestrator/` is ignored by git, so the
agent could have written either, and a planted decision must never read as the senior's. A
decision path that is a link, or lies under one, is never read (`read_decision`). It
then copies the story file as it stood at the row's first agent start, read from git rather
than from the tree, because the live story file is one the agent asking for approval can
write its own declaration into. No copy is written unless exactly one file matched then.

**An approval** (`approval_error`) names only frozen test files of the frame's anchor set, in
AD-17's run-worktree spelling: on a `workdir` row only paths under `{workdir}/`. A document
is never approved, nor an approval that gives no reason: the acceptance record names it. One
bad path fails the whole consult.

**At a `protected_path` stop** (story 1-8) a consult is offered only on a hit list with no
document in it (`qualifies`). Once `prepare` has run, `write_diff` writes the stopped
attempt's diff of every hit beside the decision file, from that tree's start SHA to the tree
the offer swept. An acceptance names exactly the hit files and gives a reason (`accepted`):
that is what the Operator's `continue` must name too.

**Known limit.** The kill reaches the agent's own process group only: a child it started in
a new session (`setsid`) escapes it. The decision is still read only from a regular file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from orchestrator.application.rules import consult
from orchestrator.application.rules.protected_paths import hit_paths, is_document
from orchestrator.application.steps import agent_tail, agent_workdir
from orchestrator.application.steps.context import (
    StepContext,
    require_cwd,
    require_env,
    require_process,
    require_workspace,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ports.workspace import Workspace
from orchestrator.domain.statuses import ParkKind
from orchestrator.domain.values import Consult

BLOCKED: ParkKind = "blocked"
IS_ANCHOR = "approved file is an anchor: {path}"
NOT_FROZEN = "approved file is not a frozen test file: {path}"
NO_REASON = "approval names no reason"
DIFFERS = "approved files differ from the hits"
#: One hit's section of the diff file.
DIFF_SECTION = "### {path}\n{diff}"


def prepare(ctx: StepContext, decision: str) -> None:
    """Kill the blocked agent's group, clear `decision` and the story baseline, then copy
    the baseline from git."""
    blocked = ctx.previous_attempt
    if blocked is not None and blocked.pgid is not None:
        require_process(ctx).kill_group(blocked.pgid)
    workspace = require_workspace(ctx, str(agent_workdir.tree(ctx)))
    story = consult.story_path(ctx.row.seq, ctx.attempt.n)
    workspace.remove(decision)
    workspace.remove(story)
    sha = require_env(ctx).story_baseline_sha
    if sha is None:
        return
    root, git = require_cwd(ctx), ctx.ports.git
    globs = agent_tail.liveness_globs(ctx.with_resolved)
    matched = [
        path
        for path in git.list_files(root, sha, agent_workdir.WHOLE_TREE)
        if any(PurePosixPath(path).full_match(pattern) for pattern in globs)
    ]
    if len(matched) != 1:
        return
    text = git.read_file(root, sha, matched[0])
    if text is not None and not workspace.is_link(story):
        workspace.write(story, text)


def read_decision(workspace: Workspace, decision: str) -> str | None:
    """The decision file's text, or `None` when it is a link or lies under one."""
    return None if workspace.is_link(decision) else workspace.read(decision)


def answered(
    ctx: StepContext, kind: ParkKind, question: str, decision: consult.Decision
) -> Consult | str:
    """The senior's answer, carrying what it approved, or why the approval fails closed.

    Only a `blocked` answer approves anything; a `verify_failed` diagnosis is told to a fresh
    redispatch, and approves nothing."""
    files = decision.approved_files if kind == BLOCKED else ()
    refused = approval_error(ctx, files)
    if refused is not None:
        return refused
    if files and not decision.reason.strip():
        return NO_REASON
    return Consult(
        kind=kind,
        question=question,
        outcome="answer",
        answer=decision.body,
        approved_files=tuple(dict.fromkeys(files)),
        reason=decision.reason,
    )


def approval_error(ctx: StepContext, files: Sequence[str]) -> str | None:
    """Why `files` cannot be approved, naming the first bad path, or `None`."""
    anchors = require_env(ctx).anchors
    workdir = agent_workdir.declared(ctx)
    for path in files:
        if is_document(path):
            return IS_ANCHOR.format(path=path)
        outside = bool(workdir) and not path.startswith(f"{workdir}/")
        if outside or path not in anchors:
            return NOT_FROZEN.format(path=path)
    return None


def qualifies(payload: Mapping[str, Any]) -> bool:
    """Whether a `protected_path` hits payload may go to a senior: hits, and no document."""
    paths = hit_paths(dict(payload))
    return bool(paths) and not any(is_document(path) for path in paths)


def same_files(approved: Sequence[str], payload: Mapping[str, Any]) -> bool:
    """Whether `approved` names exactly the hit files, as a set."""
    return set(approved) == set(hit_paths(dict(payload)))


def write_diff(ctx: StepContext, entry: Mapping[str, Any]) -> None:
    """Write the stopped attempt's diff of every hit beside the decision file; nothing
    through a link, which the agent could have planted in the ignored folder."""
    workspace = require_workspace(ctx, str(agent_workdir.tree(ctx)))
    path = consult.diff_path(ctx.row.seq, ctx.attempt.n)
    workspace.remove(path)
    if workspace.is_link(path):
        return
    hits = hit_paths(dict(entry.get(consult.HITS_KEY) or {}))
    sections = [DIFF_SECTION.format(path=hit, diff=_diff(ctx, hit)) for hit in hits]
    workspace.write(path, "\n".join(sections))


def _diff(ctx: StepContext, hit: str) -> str:
    """One hit's diff in its own tree: the workdir from `start_sha`, the root from
    `root_start_sha` on a `workdir` row, else the one tree from `start_sha`."""
    at, sha, name = _tree_of(ctx, ctx.previous_attempt, hit)
    return ctx.ports.git.diff(at, sha, name) if sha is not None else ""


def _tree_of(ctx: StepContext, stopped: Attempt | None, hit: str) -> tuple[Path, str | None, str]:
    root, workdir = require_cwd(ctx), agent_workdir.declared(ctx)
    start = stopped.start_sha if stopped is not None else None
    if not workdir:
        return root, start, hit
    if hit.startswith(f"{workdir}/"):
        return root / workdir, start, hit.removeprefix(f"{workdir}/")
    return root, stopped.root_start_sha if stopped is not None else None, hit


def accepted(
    question: str, payload: Mapping[str, Any], decision: consult.Decision
) -> Consult | str:
    """The senior's acceptance of the hits, or why it fails closed."""
    if not same_files(decision.approved_files, payload):
        return DIFFERS
    if not decision.reason.strip():
        return NO_REASON
    return Consult(
        kind=consult.PROTECTED_PATH,
        question=question,
        outcome=consult.ACCEPT,
        approved_files=hit_paths(dict(payload)),
        reason=decision.reason,
    )
