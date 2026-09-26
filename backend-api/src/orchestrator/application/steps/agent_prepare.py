"""AD-9's third and fourth side effects: **the orchestrator's own writes, and the prepare
commit that puts them behind `start_sha`** — everything between the WIP sweep and the
attempt's start half, and nothing else.

Split out of `steps/agent.py` for the reason `agent_tail.py`, `agent_answer.py` and
`agent_workdir.py` were: that module is at its 400-line cap, and this is one subject of its
own. `agent.py` imports this module and re-exports the four payload names below, so
`steps.agent.PREPARE_MESSAGE` and `steps.agent.CONTEXT_HEADING` stay reachable where they
always were, and nothing here imports `agent.py` back.

**Why the phase exists at all** (AD-17, FR-31). 5.6 attributes a range: everything between
`start_sha` and `end_sha` is the agent's, and an anchor inside it is a `protected_path` park
with that agent's name on it. So every write the *orchestrator* makes for a dispatch — the
Answer archive's rename, AD-13's de-ambiguation, `project-context.md`, the `## Verify
Failure` section a redispatch appends — has to be committed before that sha is read. An
uncommitted one would sit in the tree the agent is handed and come back as the agent's edit.

**A git failure here is a park, with git's own words** (Operator decision, 2026-09-26; hard
rule 7). This phase runs three kinds of git command — the archive's tracked-ness read,
`stage`, `commit` — and let every `GitError` escape to the registry's catch-all, which
records the exception's class name and nothing else. What the Operator saw for it was
`internal: GitError`, an empty `log_tail` and no harness: a stop with no way to tell a
vanished pathspec from an unwritable worktree, and one whose `internal` park kind does not
admit the `answer` the crash had just consumed (AD-13's table). `_park` is `git_commit.py`'s,
verbatim in shape and for the same reason — no `agent` row leaves a git failure unhandled.

**Nothing here decides a status.** The park is the one exception AD-8 allows a `StepExecutor`:
a `StepResult` carrying a `Park` is what `apply_step_result` reads, not a status this module
wrote.
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from orchestrator.application.rules.protected_paths import uncommitted
from orchestrator.application.steps import agent_answer, agent_tail
from orchestrator.application.steps.context import (
    StepContext,
    redispatched,
    require_cwd,
    require_env,
    require_workspace,
    resolved_text,
)
from orchestrator.application.story_file import after_verify
from orchestrator.application.templates.agent_row import SPEC_FOLDER_KEY, STORY_ID_KEY
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.values import Park, StepResult

log = structlog.get_logger(__name__)

#: The commit this phase places, and the document it writes before placing it.
PREPARE_MESSAGE = "orchestrator: prepare story {id} attempt {n}"
CONTEXT_FILE = "project-context.md"
CONTEXT_HEADING = "## Context files"
CONTEXT_MISSING = "context path missing: {path}"

#: The reason a git command in this phase parks with — `git_commit.py`'s `commit failed`
#: one subject over, so the two read as the same kind of stop in a Run's activity.
PREPARE_FAILED = "prepare failed"


def writes(ctx: StepContext) -> StepResult | None:
    """Write, stage and commit; `None` when the phase is done, a park when git refused."""
    try:
        _write_and_commit(ctx)
    except GitError as error:
        return _park(ctx, error)
    return None


def _write_and_commit(ctx: StepContext) -> None:
    """The phase itself. Every git call it makes is inside `writes`'s one `except`."""
    moved = (*agent_answer.archive_with_answer(ctx), *agent_tail.archive_ambiguous(ctx))
    written = (_context_document(ctx), _verify_failure(ctx))
    targets = [*moved, *(target for target in written if target is not None)]
    if not targets:
        return
    worktree = require_cwd(ctx)
    git = ctx.ports.git
    for target in targets:
        git.stage(worktree, target)
    if not _staged(git.status(worktree), targets):
        return
    git.commit(worktree, PREPARE_MESSAGE.format(id=_text(ctx, STORY_ID_KEY), n=ctx.attempt.n))


def _park(ctx: StepContext, error: GitError) -> StepResult:
    """A write, staging, status or commit command that failed for a git reason — the shape
    `git_commit.py`, `git.submodule`, `git.push`, `git.sync` and `git.merge` all park with,
    so this phase never leaves an unhandled `GitError` for the executor registry to report
    as the exception's class name alone."""
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        output_ref=error.output,
        reason=PREPARE_FAILED,
        park=Park(kind="misconfigured", reason=PREPARE_FAILED, path=ctx.row.path),
    )


def _staged(status: str, targets: Sequence[str]) -> bool:
    """Whether staging `targets` reached the index — a harness's own leftover work can dirty
    a path this row never touched, and reading *that* as "something to commit" attempted a
    commit of nothing whenever a target's `stage` was a no-op (`GitError`: nothing added)."""
    names = frozenset(targets)
    return any(change.path in names for change in uncommitted(status))


def _verify_failure(ctx: StepContext) -> str | None:
    """FR-10: the Story file a `verify` row sent back, at `in-progress` and carrying what
    failed. Nothing is written when the walker resolved no facts, or when the glob names
    other than one file — a rewrite on a guess is the ambiguity liveness refuses."""
    if not redispatched(ctx):
        return None
    fail = require_env(ctx).verify_failure
    matches = agent_tail.story_files(ctx) or ()
    if fail is None or len(matches) != 1:
        return None
    workspace = require_workspace(ctx, ctx.cwd)
    text = workspace.read(matches[0]) or ""
    workspace.write(matches[0], after_verify(text, fail.command, fail.exit_code, fail.log_tail))
    return matches[0]


def _context_document(ctx: StepContext) -> str | None:
    """`{spec_folder}/project-context.md`, or `None` when the row names no spec folder; a
    path the worktree lacks is logged and left out, and the heading is always written."""
    spec_folder = _text(ctx, SPEC_FOLDER_KEY)
    if not spec_folder:
        return None
    workspace = require_workspace(ctx, ctx.cwd)
    project = require_env(ctx).project
    kept = []
    for path in project.context_paths:
        if workspace.exists(path):
            kept.append(f"- {path}")
        else:
            log.info(CONTEXT_MISSING.format(path=path), path=ctx.row.path, context_path=path)
    target = f"{spec_folder}/{CONTEXT_FILE}"
    body = "\n".join([project.context_text, "", CONTEXT_HEADING, "", *kept])
    workspace.write(target, f"{body}\n")
    return target


def _text(ctx: StepContext, key: str) -> str:
    return resolved_text(ctx.with_resolved, key)
