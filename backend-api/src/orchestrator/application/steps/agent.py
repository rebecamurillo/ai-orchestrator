"""The `agent` kind: preparing a worktree for a coding agent, and dispatching one (AD-9,
AD-10, AD-14, FR-14). What the dispatch *reached* is `agent_tail`'s: it records the attempt
and routes on the Story file the agent wrote (FR-16), at gate `liveness` either way.

**AD-9's side-effect order is the shape of `execute`, verbatim**: orphan control, WIP commit,
the orchestrator's own writes, prepare commit, `start_sha`, prompt, dispatch, `mark_finished`.
The harness lookup runs first, being a pure read: a row naming a harness this instance lacks
must park without leaving a commit behind. The harness then receives exactly what
`HarnessEnv` returned and nothing of this process's own (AD-5, AD-10).

**Three writes, three units of work** (AD-8): `mark_started` before the process exists, the
`pgid` update between `Harness.start` and `Harness.wait`, `mark_finished` after it exits. That
middle write is the one thing a *resumed* session skips — `Harness.resume` is a single call.

**Orphan control is what makes a restart safe** (AD-14, FR-12): a previous attempt with a
`pgid` and no `end_sha` is a harness a dead backend left running. The discriminator cannot be
`ended_at` — `start_attempt` already stamps that on an attempt it finds open after a restart,
which is the very case this guards — while `end_sha` is written only by the tail.

**One resume reaches this module and dispatches nothing.** A `continue` carrying accepted
files runs only the check and routing over the previous attempt — `agent_tail.re_check`
handles it before any new commits are placed in front of the range it reads.

**Three re-dispatches reach this module and are not the same dispatch** (AD-9, AD-13): the
Template's own `retry`; a person's *Retry* from a stop; and a `verify` redispatch that
hands the agent its file back at `in-progress` with a `## Verify Failure` section (FR-10).
`context.retrying`, `context.operator_retry` and `context.redispatched` tell them apart.

**`with {workdir}` moves the dispatch, not the worktree** (AD-9, AD-17 — ratified
2026-09-23, hub-Run initiative workflow). The harness runs in that submodule's checkout and
every git fact the attempt records is that repository's; the orchestrator's own writes and
every `Workspace` read stay at the run worktree root, because the specs live in the hub.
Which tree answers which question is `agent_workdir.py`'s whole subject, including the
spec-path contract H3's templates encode and the dual-tree protected-path check; a row that
declares no `workdir` reaches exactly the calls it always did.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import structlog

from orchestrator.application.rules.protected_paths import uncommitted
from orchestrator.application.steps import (
    agent_answer,
    agent_prompt,
    agent_render,
    agent_skill,
    agent_tail,
    agent_workdir,
)
from orchestrator.application.steps.context import (
    StepContext,
    committed,
    log_path,
    redispatched,
    require_cwd,
    require_env,
    require_harness_env,
    require_harnesses,
    require_process,
    require_run,
    require_workspace,
    resolved_text,
    retrying,
)
from orchestrator.application.steps.registry import register
from orchestrator.application.story_file import after_verify
from orchestrator.application.templates.agent_row import (
    SPEC_FOLDER_KEY,
    STORY_ID_KEY,
)
from orchestrator.application.templates.rows import STALL_KEY, TIMEOUT_KEY
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.harness import Harness
from orchestrator.domain.values import Park, StepResult

log = structlog.get_logger(__name__)

#: The kind this module implements (AD-9: named here, beside the executor, or nowhere).
KIND = "agent"

#: The `with` keys this module reads, flat, the way `agent_row.py` writes them on the row.
HARNESS_KEY = "harness"
MODEL_KEY = "model"

#: The prompt, in the pieces FR-14 pins. Asserted verbatim by the prompt tests.
DISPATCH = (
    "Run the skill {skill} in folder+id dispatch mode: "
    "spec folder {spec_folder}, story id {story_id}."
)
#: How a retry prompt reaches a *new* session: in front of the dispatch sentence the session
#: has not been told yet. A resumed one is sent the retry prompt alone.
RETRY_PROMPT = "{retry} {dispatch}"

#: The two commits this module makes, and the documents it writes between them. The WIP one
#: is `agent_workdir`'s — the tree it lands in is that module's question — and re-exported
#: here, beside `WHOLE_TREE`, so this module's own name still answers "what does an `agent`
#: row commit" and "what does it freeze", the way `DISPATCH` is named here and in
#: `agent_prompt.py` both (H4, 2026-09-23).
WIP_MESSAGE = agent_workdir.WIP_MESSAGE
WHOLE_TREE = agent_workdir.WHOLE_TREE
PREPARE_MESSAGE = "orchestrator: prepare story {id} attempt {n}"
CONTEXT_FILE = "project-context.md"
CONTEXT_HEADING = "## Context files"
CONTEXT_MISSING = "context path missing: {path}"

#: The reasons this row leaves, and what an interrupted attempt carries instead of one.
UNKNOWN_HARNESS = "harness misconfigured: unknown harness {name}"
INTERRUPTED = "interrupted"

#: git's own crash-recovery lock, and how long this row waits for git to clear it (AD-14).
INDEX_LOCK = ".git/index.lock"
LOCK_POLL_SECONDS, LOCK_TIMEOUT_SECONDS = 1.0, 30.0

#: No wall-clock deadline by default (operator revision 2026-09-15: 90-min kill → stall).
DEFAULT_TIMEOUT_MIN = None
#: Minutes of filesystem silence before the stall detector kills the process (FR-10).
DEFAULT_STALL_MIN = 30


@dataclass(frozen=True)
class _Dispatch:
    """One dispatch, decided before the span opens: the calls share these five facts.
    `resume_id` is the session to continue, or `None` for a dispatch that starts one."""

    harness: Harness
    attempt: Attempt
    prompt: str
    session_id: str
    resume_id: str | None = None


class AgentExecutor:
    """Prepare the worktree, dispatch the harness, record the attempt. Decide nothing."""

    def execute(self, ctx: StepContext) -> StepResult:
        accepted = agent_tail.re_check(ctx)
        if accepted is not None:
            return accepted
        found = _harness(ctx)
        if isinstance(found, StepResult):
            return found
        # beside the harness lookup and for its reason: a row naming a folder that is no
        # initialized submodule — or a skill this instance cannot resolve, which a harness
        # answers by improvising — must park before any commit is placed (AD-9, H4).
        misconfigured = agent_workdir.verify(ctx) or agent_skill.verify(ctx)
        if misconfigured is not None:
            return misconfigured
        _orphan_control(ctx)
        agent_workdir.wip_commit(ctx)
        mode = ctx.resume_signal.payload.get("mode") if ctx.resume_signal else None
        workflow: str | None = None
        if mode != "session":
            _prepare_writes(ctx)
            # before `_start`, so a renderer that failed parks without leaving an attempt
            # open; the snapshot itself is gitignored and reaches neither commit nor sha.
            rendered = agent_render.prerendered_workflow(ctx, found)
            if isinstance(rendered, StepResult):
                return rendered
            workflow = rendered
        return _dispatch(ctx, found, _start(ctx), workflow)


def compose_prompt(
    with_resolved: Mapping[str, Any],
    resume_signal: GateRecord | None,
    previous_attempt: Attempt | None,
) -> str:
    """Delegates to `agent_prompt.compose_prompt` (FR-14, AD-7, AD-9)."""
    return agent_prompt.compose_prompt(with_resolved, resume_signal, previous_attempt)


def _harness(ctx: StepContext) -> Harness | StepResult:
    """The adapter this row's `harness:` names, or the park an unknown name is."""
    name = resolved_text(ctx.with_resolved, HARNESS_KEY)
    found = require_harnesses(ctx).get(name)
    if found is not None:
        return found
    reason = UNKNOWN_HARNESS.format(name=name)
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        reason=reason,
        park=Park(kind="misconfigured", reason=reason, path=ctx.row.path),
    )


def _orphan_control(ctx: StepContext) -> None:
    """Kill orphan process, wait on git lock, close interrupted attempt (AD-14, FR-12)."""
    previous = ctx.previous_attempt
    if previous is None or previous.pgid is None or previous.end_sha is not None:
        return
    require_process(ctx).kill_group(previous.pgid)
    workspace = require_workspace(ctx, ctx.cwd)
    waited = 0.0
    while waited < LOCK_TIMEOUT_SECONDS and workspace.exists(INDEX_LOCK):
        ctx.ports.clock.sleep(LOCK_POLL_SECONDS)
        waited += LOCK_POLL_SECONDS
    closed = previous.model_copy(
        update={"status": "error", "ended_at": ctx.ports.clock.now(), "output_ref": INTERRUPTED}
    )
    committed(ctx, lambda attempts: attempts.mark_finished(closed))


def _prepare_writes(ctx: StepContext) -> None:
    """Orchestrator writes + prepare commit (skipped for session-mode delivery)."""
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


def _start(ctx: StepContext) -> Attempt:
    """The start half, committed alone, before the process exists: the start SHAs after both
    commits, `pgid` `None` until the harness answers (AD-8, AD-14). Which tree each SHA and
    the frozen test set are read from is `agent_workdir.start_shas`'s (AD-17)."""
    started = ctx.attempt.model_copy(
        update={
            **agent_workdir.start_shas(ctx),
            "pgid": None,
            "harness": _text(ctx, HARNESS_KEY),
            "model": (_text(ctx, MODEL_KEY) or None),
        }
    )
    committed(ctx, lambda attempts: attempts.mark_started(started))
    return started


def _dispatch(
    ctx: StepContext, harness: Harness, attempt: Attempt, workflow: str | None = None
) -> StepResult:
    """Dispatch inside the attempt's span; an unwired tracer degrades to `""` (AD-11)."""
    dispatch = _planned(ctx, harness, attempt, workflow)
    tracer = ctx.ports.tracer
    if tracer is None:
        return _run(ctx, dispatch, "")
    with tracer.attempt_span(require_run(ctx), ctx.row, attempt) as span:
        return _run(ctx, dispatch, span.traceparent)


def _planned(
    ctx: StepContext, harness: Harness, attempt: Attempt, workflow: str | None = None
) -> _Dispatch:
    """Which of the three dispatches this is, and what it carries (FR-16, AD-10, AD-13).
    `compose_prompt` never sees a retry prompt: a resumed session already holds the context
    that sentence would repeat, while a session that cannot be resumed — the contract said
    not to, the harness cannot, or the last attempt recorded none — is a new one, which
    needs the sentence and gets the retry prompt in front of it."""
    previous = ctx.previous_attempt
    retry = agent_tail.retry_of(ctx) if retrying(ctx) else None
    session, resumable = str(new_id()), previous.session_id if previous is not None else None
    operator_mode = ctx.resume_signal.payload.get("mode") if ctx.resume_signal else None
    can_res = harness.capabilities.resume and resumable is not None
    tpl_ok = retry is not None and retry.resume_session
    if operator_mode == "session" and can_res:
        return _Dispatch(harness, attempt, _session_message(ctx), session, resumable)
    if operator_mode != "restart" and tpl_ok and can_res and retry is not None:
        return _Dispatch(harness, attempt, retry.prompt, session, resumable)
    prompt_file_content: str | None = None
    if agent_prompt.PROMPT_FILE_KEY in ctx.with_resolved:
        filename = str(ctx.with_resolved[agent_prompt.PROMPT_FILE_KEY])
        prompt_file_content = require_workspace(ctx, ctx.cwd).read(filename) or ""
    prompt = agent_prompt.compose_prompt(
        agent_workdir.prompt_scope(ctx),
        agent_answer.resolved_signal(ctx),
        previous,
        prompt_file_content=prompt_file_content,
        workflow_path=workflow,
    )
    if retry is not None:
        prompt = RETRY_PROMPT.format(retry=retry.prompt, dispatch=prompt)
    return _Dispatch(harness, attempt, prompt, session)


def _run(ctx: StepContext, dispatch: _Dispatch, traceparent: str) -> StepResult:
    """Start the harness, commit its group, then wait for it — AD-14's order, exactly. A
    resumed session skips the middle write: `Harness.resume` is one call, so no handle sits
    between two halves for a dead backend to lose."""
    run, environment = require_run(ctx), require_env(ctx)
    timeout_min = ctx.with_resolved.get(TIMEOUT_KEY)
    stall_min = ctx.with_resolved.get(STALL_KEY, DEFAULT_STALL_MIN)
    env = require_harness_env(ctx)(
        dispatch.attempt,
        run=run,
        project_slug=environment.project_slug,
        project_env=environment.project.env_vars,
        log_content=environment.project.log_prompt_content,
        story_id=_text(ctx, STORY_ID_KEY) or None,
        traceparent=traceparent,
    )
    # the member checkout on a `workdir` row, the worktree root otherwise: the process's own
    # folder, and therefore the one the stall detector watches (AD-9, AD-17, H4).
    dispatch_cwd = agent_workdir.tree(ctx)
    if dispatch.resume_id is not None:
        resumed = dispatch.harness.resume(
            cwd=dispatch_cwd,
            session_id=dispatch.resume_id,
            message=dispatch.prompt,
            env=env,
            timeout_min=timeout_min,
            log_path=log_path(ctx),
            stall_min=stall_min,
        )
        return agent_tail.finish(ctx, dispatch.attempt, resumed, timeout_min, stall_min)
    handle = dispatch.harness.start(
        cwd=dispatch_cwd,
        prompt=dispatch.prompt,
        env=env,
        model=(_text(ctx, MODEL_KEY) or None),
        session_id=dispatch.session_id,
        budget_usd_remaining=run.budget_usd - run.spend_usd if run.budget_usd is not None else None,
        timeout_min=timeout_min,
        log_path=log_path(ctx),
        stall_min=stall_min,
    )
    # the session travels with the group: a dead backend must leave a resumable attempt
    running = dispatch.attempt.model_copy(
        update={"pgid": handle.pgid, "session_id": handle.session_id}
    )
    try:
        committed(ctx, lambda attempts: attempts.update(running))
    except BaseException:
        # the only frame holding the handle: an escape without a kill is AD-14's orphan
        require_process(ctx).kill_group(handle.pgid)
        raise
    return agent_tail.finish(ctx, running, dispatch.harness.wait(handle), timeout_min, stall_min)


def _text(ctx: StepContext, key: str) -> str:
    """One of this row's resolved keys as a string — `STORY_ID_KEY` is the Story it works
    on, flattened onto the row by the planner (AD-7)."""
    return resolved_text(ctx.with_resolved, key)


def _session_message(ctx: StepContext) -> str:
    if ctx.resume_signal is not None and ctx.resume_signal.event == agent_answer.ANSWER_EVENT:
        return str(ctx.resume_signal.payload.get("text", ""))
    retry = agent_tail.retry_of(ctx)
    return retry.prompt if retry is not None else ""


register(KIND, AgentExecutor())
