"""The senior's process in one session turn (AD-10, AD-11, AD-14, AD-23): the sweep, the
turn's files, the start record, then a new or resumed harness session inside the attempt
span, its group committed before it is awaited, and the exit recorded. Split out of
`session_turn.py`, which reads the turn and closes it.

Every write here is the turn's own attempt row, through `attempt_writes` (AD-8). `ended_at`
is never written: a turn stays open until `session_commit` has committed and billed it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orchestrator.application.rules import consult, session
from orchestrator.application.rules.conversation import STEP_KEY, close_clause
from orchestrator.application.steps import (
    CONVERSATION_KIND,
    agent_env,
    agent_tail,
    agent_workdir,
    records,
)
from orchestrator.application.steps.agent import (
    DEFAULT_STALL_MIN,
    INDEX_LOCK,
    LOCK_POLL_SECONDS,
    LOCK_TIMEOUT_SECONDS,
)
from orchestrator.application.steps.context import (
    StepContext,
    committed,
    log_path,
    require_attempt_writes,
    require_harnesses,
    require_process,
    require_run,
    require_workspace,
    resolved_text,
)
from orchestrator.application.templates.agent_row import SPEC_FOLDER_KEY
from orchestrator.application.templates.rows import STALL_KEY
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.harness import Harness, HarnessHandle

UNKNOWN_HARNESS = "unknown harness {name}"
NOT_INSTALLED = "skill {name} is not installed on {harness}; name its repository path in with.skill"
UNDER_LINK = "reply file is under a link"
SESSION_CLOSED = "session closed"
#: The folder both turn files live under; `is_link` on it covers `.orchestrator` too.
REPLY_FOLDER = ".orchestrator/session"
#: The Run input naming its spec folder, for a parked row that resolved none of its own.
SPEC_FOLDER_INPUT = "spec_folder"
SKILL_KEY = "skill"
PERSONA_KEY = "persona"


@dataclass(frozen=True)
class Turn:
    """One turn as `session_turn.read_turn` found it: the parked row's context with the turn
    as its attempt, the Run, the session's attempts, and the scope it was opened with."""

    ctx: StepContext
    run: Run
    turns: tuple[Attempt, ...]
    scope: str


def record(ctx: StepContext, **fields: Any) -> None:
    """Write `fields` onto the turn as it is stored now, in a unit of work of its own."""

    def write(attempts: Any) -> None:
        stored = attempts.get(ctx.attempt.id)
        assert stored is not None
        attempts.update(stored.model_copy(update=fields))

    committed(ctx, write)


def git_words(error: GitError) -> str:
    return error.output.strip() or str(error)


def interrupt(ctx: StepContext, reason: str) -> None:
    """A turn a dead backend left running: kill its group, let git's lock clear, close it
    `error`. It is never dispatched again (hard rule 7)."""
    pgid = ctx.attempt.pgid
    if pgid is not None:
        require_process(ctx).kill_group(pgid)
        workspace = require_workspace(ctx, ctx.cwd)
        waited = 0.0
        while waited < LOCK_TIMEOUT_SECONDS and workspace.exists(INDEX_LOCK):
            ctx.ports.clock.sleep(LOCK_POLL_SECONDS)
            waited += LOCK_POLL_SECONDS
    record(ctx, status="error", output_ref=reason, log_path=str(log_path(ctx)))


def dispatch(turn: Turn) -> None:
    """A queued turn, from the sweep to the recorded exit; git's refusal is the turn's."""
    ctx = turn.ctx
    harness = require_harnesses(ctx).get(ctx.attempt.harness or "")
    if harness is None:
        record(ctx, status="error", output_ref=UNKNOWN_HARNESS.format(name=ctx.attempt.harness))
        return
    ref = _step_ref(turn)
    if ref is None:
        skill = str(ctx.row.with_resolved.get(SKILL_KEY) or "").strip()
        record(
            ctx,
            status="error",
            output_ref=NOT_INSTALLED.format(name=skill, harness=ctx.attempt.harness),
        )
        return
    if session.needs_sweep(turn.turns, ctx.attempt):
        try:
            records.note_commits(ctx, agent_workdir.sweep(ctx, session.WIP_MESSAGE), "session")
        except GitError as error:
            record(ctx, status="error", output_ref=git_words(error))
            return
    workspace = require_workspace(ctx, str(agent_workdir.tree(ctx)))
    # a link left in the tree would carry these writes to whatever the backend's user can
    # reach: a link at a file is removed, a link at a folder refuses the turn
    if workspace.is_link(REPLY_FOLDER):
        record(ctx, status="error", output_ref=UNDER_LINK)
        return
    for path in (consult.IGNORE_FILE, session.REPLY_FILE, session.CLOSE_FILE):
        workspace.remove(path)
    workspace.write(consult.IGNORE_FILE, consult.IGNORE_ALL)
    workspace.write(session.REPLY_FILE, "")
    started = ctx.attempt.model_copy(
        update={**agent_workdir.start_shas(ctx), "status": "running", "pgid": None}
    )
    committed(ctx, lambda attempts: attempts.mark_started(started))
    tracer = ctx.ports.tracer
    if tracer is None:
        _run(turn, harness, started, "", ref)
        return
    with tracer.attempt_span(require_run(ctx), ctx.row, started) as span:
        _run(turn, harness, started, span.traceparent, ref)


def _run(turn: Turn, harness: Harness, started: Attempt, traceparent: str, ref: str) -> None:
    """Start or resume, commit the group and the session, wait, record the exit (AD-14)."""
    ctx = turn.ctx
    handle = _start(turn, harness, started, traceparent, ref)
    running = started.model_copy(
        update={"pgid": handle.pgid, "session_id": handle.session_id or None}
    )
    try:
        still_open = _commit_group(ctx, running)
    except BaseException:
        require_process(ctx).kill_group(handle.pgid)
        raise
    if not still_open:
        require_process(ctx).kill_group(handle.pgid)
    result = harness.wait(handle)
    closed = {} if still_open else {"status": "error", "output_ref": SESSION_CLOSED}
    finished = running.model_copy(
        update={
            "status": "done" if result.exit_code == 0 else "error",
            "exit_code": result.exit_code,
            "session_id": result.session_id,
            "log_path": str(result.log_path),
            **agent_tail.usage(result),
            **closed,
        }
    )
    committed(ctx, lambda attempts: attempts.update(finished))


def _commit_group(ctx: StepContext, running: Attempt) -> bool:
    """Commit the group under the Run's row lock, and answer whether the session is still
    open: a `cancel` that took the lock first found no group to kill, so killing this one is
    then the caller's (AD-8, AD-14)."""
    with require_attempt_writes(ctx)() as writers, writers.uow:
        run = writers.runs.get_for_update(running.run_id)
        writers.attempts.update(running)
        writers.uow.commit()
    return run is not None and session.session_open(run)


def _start(
    turn: Turn, harness: Harness, started: Attempt, traceparent: str, ref: str
) -> HarnessHandle:
    """The resumed session with the text alone, or a new one opened by the skill's line."""
    ctx = turn.ctx
    tree = agent_workdir.tree(ctx)
    common: dict[str, Any] = {
        "cwd": tree,
        "env": agent_env.environment(ctx, started, traceparent),
        "model": started.model,
        "budget_usd_remaining": agent_env.remaining(require_run(ctx)),
        "timeout_min": None,
        "log_path": log_path(ctx),
        "stall_min": ctx.with_resolved.get(STALL_KEY, DEFAULT_STALL_MIN),
        "add_dirs": agent_env.add_dirs(ctx, tree),
    }
    text = _harness_text(turn, started)
    resumed = session.resumable(turn.turns, started)
    if resumed is not None:
        return harness.start_resume(session_id=resumed, message=text, **common)
    if turn.scope == session.STEP_SCOPE:
        resolved = ctx.row.with_resolved
        facts: tuple[str | None, ...] = (resolved.get(STEP_KEY), resolved.get(PERSONA_KEY))
        prompt = session.opening_line(facts, text, skill=ref)
    else:
        prompt = session.opening_line(_facts(turn), started.message)
    return harness.start(prompt=prompt, session_id=str(new_id()), **common)


def _harness_text(turn: Turn, started: Attempt) -> str:
    """The owner's message, and on a conversation step session the row's close instruction
    after a blank line; the stored message stays the owner's text alone."""
    row = turn.ctx.row
    if turn.scope != session.STEP_SCOPE or row.kind != CONVERSATION_KIND:
        return started.message
    clause = close_clause(row, started.id)
    return f"{started.message}\n\n{clause}" if clause else started.message


def _step_ref(turn: Turn) -> str | None:
    """The skill a new step session opens with; resumed turns and other scopes keep the
    senior's. A catalog that cannot answer, or raises, names the skill as written."""
    ctx = turn.ctx
    if turn.scope != session.STEP_SCOPE or session.resumable(turn.turns, ctx.attempt):
        return session.OPENING_SKILL
    catalog = ctx.ports.skill_catalog
    installed = None
    if catalog is not None:
        try:
            installed = catalog.installed_skills(ctx.attempt.harness or "")
        except Exception:
            installed = None
    return session.step_skill_ref(ctx.row.with_resolved.get(SKILL_KEY), installed)


def _facts(turn: Turn) -> tuple[str | None, ...]:
    """The opening line's values, in the skill's order (story 2-5, Decided 1)."""
    ctx, run = turn.ctx, turn.run
    spec_folder = resolved_text(agent_workdir.prompt_scope(ctx), SPEC_FOLDER_KEY)
    return (
        turn.scope,
        spec_folder or str(run.inputs.get(SPEC_FOLDER_INPUT) or ""),
        ctx.row.story_id,
        ctx.row.frame,
        run.park_kind,
        run.park_reason,
    )
