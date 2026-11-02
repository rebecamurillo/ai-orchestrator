"""What a `blocked` consult reviews a test-edit approval against (AD-17's and AD-22's
2026-11-02 amendments, hard rule 1).

**Before the senior is dispatched** (`prepare`), the consult attempt clears its own decision
path and the story baseline beside it: `.orchestrator/` is ignored by git, so the blocked
agent could have written either, and a planted decision must never read as the senior's. It
then copies the story file as it stood at the row's first agent start, read from git rather
than from the tree, because the live story file is one the agent asking for approval can
write its own declaration into. No copy is written unless exactly one file matched then.

**An approval** (`approval_error`) names only frozen test files of the frame's anchor set, in
AD-17's run-worktree spelling: on a `workdir` row only paths under `{workdir}/`. A document
is never approved. One bad path fails the whole consult.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePosixPath

from orchestrator.application.rules import consult
from orchestrator.application.rules.protected_paths import is_document
from orchestrator.application.steps import agent_tail, agent_workdir
from orchestrator.application.steps.context import (
    StepContext,
    require_cwd,
    require_env,
    require_workspace,
)
from orchestrator.domain.statuses import ParkKind
from orchestrator.domain.values import Consult

BLOCKED: ParkKind = "blocked"
IS_ANCHOR = "approved file is an anchor: {path}"
NOT_FROZEN = "approved file is not a frozen test file: {path}"


def prepare(ctx: StepContext, decision: str) -> None:
    """Clear `decision` and the story baseline, then copy the baseline from git."""
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
    if text is not None:
        workspace.write(story, text)


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
