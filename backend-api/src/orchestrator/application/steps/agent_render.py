"""Rendering the workflow snapshot before the agent is dispatched (AD-9, FR-14).

**Why the orchestrator renders and the agent does not.** A BMAD skill's `SKILL.md` asks the
agent to substitute two placeholders into a `render_skill.py` command, run it exactly once,
and read the `workflow.md` path it prints. That hand-off is the whole protocol: everything
the workflow legislates — the four steps, the frontmatter statuses, the review layers, the
halt contract — lives behind it, and an agent that fumbles it holds no protocol at all.

Measured on the `local` harness (Operator finding, 2026-09-21, run
`01a0bf7c-2fdc-714c-a7ee-92a3b0429395`): six attempts, six different fumbles. Two invented
CLI arguments to carry the dispatch facts the renderer has no parameter for
(`--spec-folder`, `--story-id`) and argparse rejected them; one substituted a skill root
that does not exist and concluded the renderer was missing; three never ran it. All six
then ignored `SKILL.md`'s "on failure, report and HALT" and improvised the story straight
from the dispatch sentence — which is why no run reached a step file, wrote a status, or
opened a review. The command is a pure function of two paths this process already knows, so
it is rendered here and the agent is handed the result.

**Skipping is not failing.** A row whose prompt is its own (`prompt`, `prompt_file`), a
harness that installs no skills, a worktree with no renderer, and a skill with no
`workflow.md` of its own each return `None` and dispatch exactly as they did before: a
target repository that never ran `repo-init` must keep working, and an operator skill
authored to `ia-agents-skills/README.md`'s own contract — `SKILL.md` alone, no renderer
entry — is not a workflow this module has anything to render (`render_skill.py` demands a
`workflow.md` for every skill it is pointed at; a skill that never shipped one was never
meant to go through it). A renderer that *is* there and fails parks the Run instead (hard
rule 7) — the silent improvisation this module exists to end is never an outcome it
produces.

**Nothing here reaches git.** `_bmad/render/` self-ignores through its own `.gitignore`, so
the snapshot never enters the agent's diff, the prepare commit, or `start_sha`.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from orchestrator.application.steps.agent_prompt import (
    PROMPT_FILE_KEY,
    PROMPT_KEY,
    SKILL_KEY,
)
from orchestrator.application.steps.context import (
    StepContext,
    log_path,
    require_cwd,
    require_process,
    require_workspace,
    resolved_text,
)
from orchestrator.domain.ports.harness import Harness
from orchestrator.domain.values import Park, StepResult

log = structlog.get_logger(__name__)

#: The renderer, where `bmad.install` leaves it in every initialised repository (AD-16).
RENDER_SCRIPT = "_bmad/scripts/render_skill.py"

#: Every long option the command may carry. `render_skill.py` takes exactly two and `uv`
#: takes one; anything else is the invention that made argparse refuse attempts 3 and 6.
ACCEPTED = ("--no-cache", "--project-root", "--skill")

#: The renderer's own success line (`render_skill.py` `main`), and its failure prefix.
FOLLOW = "read and follow "
HALT = "HALT:"

#: The render's log, beside the attempt's own so one directory holds both.
RENDER_LOG_SUFFIX = ".render"

#: What `render_skill.py::_load_sources` requires of every skill it is pointed at. A skill
#: directory with no entry of this name was never meant to render (see module docstring) —
#: checked before the renderer runs, rather than let it print its own `HALT:` for a case
#: that is not a misconfiguration.
WORKFLOW_ENTRY = "workflow.md"

#: Minutes before the runner kills the render. It reads a dozen small files and hashes
#: them; a render still going after this is wedged, not slow.
RENDER_TIMEOUT_MIN = 5

#: What a park says, and the three details it carries.
RENDER_FAILED = "workflow render failed: {detail}"
RENDER_TIMED_OUT = "workflow render timeout after {n} min"
NO_SNAPSHOT = "renderer printed no workflow path"
EXIT = "exit {code}"

#: What a skipped render logs — never a park, always a line (see the module docstring).
SKIPPED = "workflow prerender skipped"


def render_argv(worktree: Path, skill_dir: Path) -> list[str]:
    """`SKILL.md`'s own command, with both placeholders already substituted.

    One argv rather than a shell string: a worktree path holding a space is a path, not a
    word break, and nothing here builds a line a repository slug could split.
    """
    return [
        "uv",
        "run",
        "--no-cache",
        str(worktree / RENDER_SCRIPT),
        "--project-root",
        str(worktree),
        "--skill",
        str(skill_dir),
    ]


def snapshot_from(output: str) -> str | None:
    """The workflow path the renderer printed, or `None` when it printed none.

    The last such line wins: the log is appended to, so a re-render of the same sources —
    which is an ordinary idempotent outcome, not an error — leaves the earlier line above
    the current one.
    """
    found = [line[len(FOLLOW) :].strip() for line in output.splitlines() if line.startswith(FOLLOW)]
    return found[-1] if found else None


def _missing_prerequisite(ctx: StepContext, skill_dir: Path) -> str | None:
    """The first of the render's two prerequisites this row's worktree or skill lacks, or
    `None` when both are present: the worktree's own `RENDER_SCRIPT`, and the skill's own
    `WORKFLOW_ENTRY`. One function so `prerendered_workflow` reports either as a single skip
    rather than two near-identical branches."""
    if not require_workspace(ctx, ctx.cwd).exists(RENDER_SCRIPT):
        return RENDER_SCRIPT
    if not require_workspace(ctx, str(skill_dir)).exists(WORKFLOW_ENTRY):
        return WORKFLOW_ENTRY
    return None


def prerendered_workflow(ctx: StepContext, harness: Harness) -> str | StepResult | None:
    """The rendered `workflow.md` for this row's skill: a path, a park, or `None`.

    `None` is "this row renders nothing" and the caller dispatches unchanged — including a
    skill directory that carries no `workflow.md` of its own (`ia-agents-skills/README.md`'s
    contract asks only for `SKILL.md`; the renderer's own `workflow.md` requirement is not
    part of it). A `StepResult` is a renderer that was present and failed, which parks
    rather than dispatching a prompt whose protocol never loaded.
    """
    skill = _skill_of(ctx)
    if skill is None or harness.skills_dir is None:
        return None
    worktree = Path(require_cwd(ctx))
    skill_dir = harness.skills_dir / skill
    missing = _missing_prerequisite(ctx, skill_dir)
    if missing is not None:
        log.info(SKIPPED, path=ctx.row.path, reason=missing, skill=skill)
        return None
    output_log = Path(f"{log_path(ctx)}{RENDER_LOG_SUFFIX}")
    process = require_process(ctx)
    handle = process.start(
        render_argv(worktree, skill_dir),
        cwd=worktree,
        env={},
        timeout_min=RENDER_TIMEOUT_MIN,
        log_path=output_log,
    )
    outcome = process.wait(handle)
    if outcome.timed_out:
        return _parked(ctx, RENDER_TIMED_OUT.format(n=RENDER_TIMEOUT_MIN), output_log)
    printed = require_workspace(ctx, str(output_log.parent)).read(output_log.name) or ""
    if outcome.exit_code != 0:
        detail = _detail(printed, outcome.exit_code)
        return _parked(ctx, RENDER_FAILED.format(detail=detail), output_log)
    snapshot = snapshot_from(printed)
    if snapshot is None:
        return _parked(ctx, RENDER_FAILED.format(detail=NO_SNAPSHOT), output_log)
    return snapshot


def _skill_of(ctx: StepContext) -> str | None:
    """The skill this row dispatches, or `None` when the row carries its own prompt.

    `prompt` and `prompt_file` are the two forms that name no skill to render: whatever
    they hold is what the harness is asked, verbatim (`agent_prompt.compose_prompt`).
    """
    if PROMPT_KEY in ctx.with_resolved or PROMPT_FILE_KEY in ctx.with_resolved:
        return None
    return resolved_text(ctx.with_resolved, SKILL_KEY) or None


def _detail(printed: str, code: int | None) -> str:
    """The renderer's own `HALT:` line when it wrote one, else the exit code it left."""
    halted = [line.strip() for line in printed.splitlines() if line.startswith(HALT)]
    return halted[-1] if halted else EXIT.format(code=code)


def _parked(ctx: StepContext, reason: str, output_log: Path) -> StepResult:
    """A renderer that failed: the row errors on the log the Operator opens."""
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        output_ref=str(output_log),
        log_path=str(output_log),
        reason=reason,
        park=Park(kind="misconfigured", reason=reason, path=ctx.row.path),
    )
