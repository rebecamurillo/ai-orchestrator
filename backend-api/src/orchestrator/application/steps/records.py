"""The one entry point an executor records through (AGENTS.md "Data capture").

A side record: every function returns before any git call when `record_writes` is unset, and
swallows and logs every exception, so no executor's `StepResult` depends on it.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path, PurePosixPath

import structlog

from orchestrator.application.steps.context import (
    StepContext,
    require_cwd,
    require_env,
    resolved_text,
)
from orchestrator.application.use_cases.run_records import GITMODULES, submodule_url
from orchestrator.domain.entities.run_records import (
    MadeBy,
    RunCommit,
    RunRepositoryRecord,
)
from orchestrator.domain.ids import new_id

log = structlog.get_logger(__name__)

RECORD_FAILED = "run record failed"
FALLBACK_REF = "HEAD"


def note_member(ctx: StepContext, workdir: str) -> None:
    """Write the `run_repository` row of `workdir` when the Run has none yet."""
    if ctx.ports.record_writes is None:
        return
    try:
        path = str(PurePosixPath(workdir))
        with ctx.ports.record_writes() as ports:
            run_id = ctx.attempt.run_id
            if ports.repositories.get(run_id, path) is not None:
                return
            env, git = require_env(ctx), ctx.ports.git
            recorded = env.worktree_at(ctx.cwd)
            text = git.read_file(
                require_cwd(ctx), recorded.branch if recorded else FALLBACK_REF, GITMODULES
            )
            url = submodule_url(text, path, env.repository_url)
            run = env.run
            base = str((run.inputs.get("base_branch") if run else None) or env.default_branch)
            found = git.ls_remote(url, base) if url else None
            branch = (run.inputs.get("branch") if run else None) or resolved_text(
                ctx.with_resolved, "branch"
            )
            ports.repositories.add(
                RunRepositoryRecord(
                    id=new_id(),
                    run_id=run_id,
                    path=path,
                    remote_url=url,
                    base_branch=base,
                    branch=str(branch or ""),
                    base_tip=found.sha if found is not None else "",
                )
            )
            ports.uow.commit()
    except Exception:
        log.exception(RECORD_FAILED, what="member", path=workdir)


def note_commits(
    ctx: StepContext, commits: Iterable[tuple[str, str | None]], made_by: MadeBy
) -> None:
    """One `run_commit` row per `(path, sha)` with a SHA, in one commit of the scope."""
    if ctx.ports.record_writes is None:
        return
    try:
        found = [(str(PurePosixPath(path)), sha) for path, sha in commits if sha]
        if not found:
            return
        with ctx.ports.record_writes() as ports:
            now = ctx.ports.clock.now()
            for path, sha in found:
                ports.commits.add(
                    RunCommit(
                        id=new_id(),
                        run_id=ctx.attempt.run_id,
                        path=path,
                        sha=sha,
                        made_by=made_by,
                        at=now,
                    )
                )
            ports.uow.commit()
    except Exception:
        log.exception(RECORD_FAILED, what="commits", made_by=made_by)


def note_head_commit(ctx: StepContext, path: str, tree: Path, made_by: MadeBy) -> None:
    """Record the commit `tree` stands on."""
    if ctx.ports.record_writes is None:
        return
    try:
        note_commits(ctx, ((path, ctx.ports.git.head_sha(tree)),), made_by)
    except Exception:
        log.exception(RECORD_FAILED, what="head", path=path)


def note_pushed(ctx: StepContext, path: str, tree: Path) -> None:
    """Set `head_pushed` of `path` to what `tree` stands on."""
    if ctx.ports.record_writes is None:
        return
    try:
        sha = ctx.ports.git.head_sha(tree)
        if sha is None:
            return
        with ctx.ports.record_writes() as ports:
            ports.repositories.set_head_pushed(ctx.attempt.run_id, str(PurePosixPath(path)), sha)
            ports.uow.commit()
    except Exception:
        log.exception(RECORD_FAILED, what="pushed", path=path)
