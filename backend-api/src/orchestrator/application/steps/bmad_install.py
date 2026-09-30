"""The `bmad.install` kind: the method into a target repository, once (AD-16, FR-30).

**One pinned version, from the instance.** `BMAD_VERSION` is what this image's skills and its
`scripts/harness/*.sh` were built from (AD-16), so a repository initialised by this instance
gets that version and not "latest": a repository whose `_bmad/` and whose orchestrator
disagree is exactly the version skew AD-16 exists to prevent. `RunEnvironment.bmad_version`
carries it — read once in `infrastructure/settings.py`, like every other instance value.

**All three tool folders, because the harness is chosen per Run.** The Operator picks
`claude`, `codex` or `local` when they start a Run, and a repository initialised for one of
them would refuse the other two later.

**Nothing outside `_bmad/` and the spec folders is committed** (AD-16). `bmad-method` also
writes `.claude/skills/bmad-*`, `.agents/skills/bmad-*` and `.opencode/commands/bmad-*` into
the repository — skills for claude and codex, commands for opencode — and this row appends
the three ignore lines that keep all of them out of the commit `git.commit` makes next.
Appended, never rewritten: a repository that already ignores other things keeps ignoring
them, and running this row twice adds nothing a second time.

The install itself goes through `ProcessRunner` like every other command (AD-14), so it is
timed by the row's own `timeout_min` and killed as a group if it outlives it. `env={}`: the
Project's own variables are Epic 5's decryption work, and no credential of this instance
reaches an `npx` process (AD-5).
"""

from __future__ import annotations

from orchestrator.application.steps.context import (
    StepContext,
    log_path,
    require_cwd,
    require_env,
    require_process,
    require_workspace,
)
from orchestrator.application.steps.registry import register
from orchestrator.application.templates.rows import TIMEOUT_KEY
from orchestrator.domain.statuses import ParkKind
from orchestrator.domain.values import Park, StepResult

#: The kind this module implements (AD-9: named here, beside the executor, or nowhere).
KIND = "bmad.install"

#: `KIND_META["bmad.install"].timeout_default_min`; the shipped exemplar declares the same 30.
DEFAULT_TIMEOUT_MIN = 30

#: The command, in the shape `scripts/harness/_common.sh` already installs the skill stubs
#: with — one argv, so nothing here builds a shell string a repository slug could break.
INSTALL_COMMAND = (
    "npx",
    "--yes",
    "bmad-method@{version}",
    "install",
    "--yes",
    "--modules",
    "bmm",
    "--tools",
    "claude-code,codex,opencode",
    "--directory",
    "{worktree}",
)

#: The file the ignore lines are appended to, and the lines themselves (AD-16).
GITIGNORE = ".gitignore"
IGNORED = (".claude/skills/bmad-*", ".agents/skills/bmad-*", ".opencode/commands/bmad-*")

#: What a failed install parks the Run with, and what a killed one leaves instead.
INSTALL_FAILED = "bmad install failed: exit {code}"
TIMED_OUT = "timeout {path} after {n} min"

#: What the row says when it added nothing to `.gitignore` because both lines were there.
ALREADY_IGNORED = "already ignored"


class BmadInstallExecutor:
    """Run the pinned `bmad-method` installer in the worktree, then ignore its tool folders."""

    def execute(self, ctx: StepContext) -> StepResult:
        env = require_env(ctx)
        worktree = require_cwd(ctx)
        timeout_min = ctx.with_resolved.get(TIMEOUT_KEY, DEFAULT_TIMEOUT_MIN)
        output = log_path(ctx)
        process = require_process(ctx)
        command = [
            part.format(version=env.bmad_version, worktree=worktree) for part in INSTALL_COMMAND
        ]
        handle = process.start(
            command, cwd=worktree, env={}, timeout_min=timeout_min, log_path=output
        )
        outcome = process.wait(handle)
        if outcome.timed_out:
            reason = TIMED_OUT.format(path=ctx.row.path, n=timeout_min)
            return _parked(ctx, reason, str(output), "timeout")
        if outcome.exit_code != 0:
            reason = INSTALL_FAILED.format(code=outcome.exit_code)
            return _parked(ctx, reason, str(output), "misconfigured")
        added = _ignore_skill_folders(ctx)
        return StepResult(
            status="done",
            gate=ctx.row.gate,
            output_ref=str(output),
            log_path=str(output),
            reason=None if added else ALREADY_IGNORED,
        )


def _ignore_skill_folders(ctx: StepContext) -> bool:
    """Append whichever of the three lines the worktree's `.gitignore` does not hold."""
    workspace = require_workspace(ctx, ctx.cwd)
    current = workspace.read(GITIGNORE) or ""
    lines = current.splitlines()
    missing = [line for line in IGNORED if line not in lines]
    if not missing:
        return False
    body = "\n".join([*lines, *missing])
    workspace.write(GITIGNORE, f"{body}\n")
    return True


def _parked(ctx: StepContext, reason: str, output: str, kind: ParkKind) -> StepResult:
    """A failed or killed install: the row errors on the log the Operator opens."""
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        output_ref=output,
        log_path=output,
        reason=reason,
        park=Park(kind=kind, reason=reason, path=ctx.row.path),
    )


register(KIND, BmadInstallExecutor())
