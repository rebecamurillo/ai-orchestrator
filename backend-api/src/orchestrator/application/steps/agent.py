"""The `agent` kind: preparing a worktree for a coding agent, and dispatching one (AD-9,
AD-10, AD-14, FR-14). What the dispatch *reached* is `agent_tail`'s: it records the attempt
and routes on the Story file the agent wrote (FR-16), at gate `liveness` either way.

**AD-9's side-effect order is the shape of `execute`, verbatim**: orphan control, WIP commit,
the orchestrator's own writes, prepare commit, `start_sha`, prompt, dispatch, `mark_finished`.
The three in the middle are `_prepare`'s, and what each of them *is* lives one module over —
the WIP sweep in `agent_workdir.py`, the writes and the prepare commit in `agent_prepare.py`
— but the order stays here, where the sequence is the rule. The harness lookup runs first,
being a pure read: a row naming a harness this instance lacks must park without leaving a
commit behind. The harness then receives exactly what `HarnessEnv` returned and nothing of
this process's own (AD-5, AD-10).

**No git failure leaves this kind as an exception class** (Operator decision, 2026-09-26).
Every phase that runs a git command answers a park carrying git's own output instead of
raising, because an unhandled one reaches `steps/registry.py`'s catch-all, which records
`internal: {ClassName}`, no output and no harness — a stop the Operator can neither read
nor, by AD-13's table, answer.

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
`context.retrying`, `context.operator_retry` and `context.redispatched` tell them apart. A
verify redispatch's own *fresh* dispatch also leads with the row's `redispatch` prompt
clause, filled from the same failure the file section quotes (`agent_prompt.redispatch_clause`)
— once, on the attempt `context.redispatched` names, never on a retry that follows it.

**`with {workdir}` moves the dispatch, not the worktree** (AD-9, AD-17 — ratified
2026-09-23, hub-Run initiative workflow). The harness runs in that submodule's checkout and
every git fact the attempt records is that repository's; the orchestrator's own writes and
every `Workspace` read stay at the run worktree root, because the specs live in the hub.
Which tree answers which question is `agent_workdir.py`'s whole subject, including the
spec-path contract H3's templates encode and the dual-tree protected-path check; a row that
declares no `workdir` reaches exactly the calls it always did.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import structlog

from orchestrator.application.steps import (
    agent_answer,
    agent_prepare,
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
    operator_retry,
    redispatched,
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
from orchestrator.application.templates.agent_row import (
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

#: The two commits this module makes, and the documents it writes between them. The WIP one
#: is `agent_workdir`'s — the tree it lands in is that module's question — and re-exported
#: here, beside `WHOLE_TREE`, so this module's own name still answers "what does an `agent`
#: row commit" and "what does it freeze" (H4, 2026-09-23). The prompt itself has no
#: constant to re-export any more: since the Operator decision of 2026-09-27 every sentence
#: is the row's own `prompts` clause, and `agent_prompt.py` only fills and joins them.
WIP_MESSAGE = agent_workdir.WIP_MESSAGE
WHOLE_TREE = agent_workdir.WHOLE_TREE
PREPARE_MESSAGE = agent_prepare.PREPARE_MESSAGE
CONTEXT_FILE = agent_prepare.CONTEXT_FILE
CONTEXT_HEADING = agent_prepare.CONTEXT_HEADING
CONTEXT_MISSING = agent_prepare.CONTEXT_MISSING

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
        prepared = _prepare(ctx, found)
        if isinstance(prepared, StepResult):
            return prepared
        return _dispatch(ctx, found, _start(ctx), prepared)


def _prepare(ctx: StepContext, harness: Harness) -> StepResult | str | None:
    """AD-9's second, third and fourth side effects, in order: the WIP sweep, the
    orchestrator's own writes with the prepare commit, and the prerendered workflow.

    Answers the workflow path the dispatch carries — or the park any of the three is, which
    the caller tells apart by type. All three make git or filesystem calls that can refuse,
    and **each refusal is a park with the failure's own words**: an unhandled one reaches
    the Operator as the exception's class name and an `internal` stop (`agent_prepare.py`,
    Operator decision 2026-09-26).

    A session-mode delivery skips the two documents and the prerendered workflow — the
    session it resumes already holds everything they would place in front of it (AD-13) —
    but **not the archives**: FR-18's rename is the orchestrator's own bookkeeping, and
    `_session_message` reads the Answer clause's condition back out of it, so the sweep and
    `moves_only` writes still run (Operator decision, 2026-09-26).
    """
    swept = agent_workdir.wip_commit(ctx)
    if swept is not None:
        return swept
    mode = ctx.resume_signal.payload.get("mode") if ctx.resume_signal else None
    if mode == "session":
        return agent_prepare.writes(ctx, moves_only=True)
    refused = agent_prepare.writes(ctx)
    if refused is not None:
        return refused
    # before `_start`, so a renderer that failed parks without leaving an attempt
    # open; the snapshot itself is gitignored and reaches neither commit nor sha.
    return agent_render.prerendered_workflow(ctx, harness)


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
    """Which of the three dispatches this is (FR-16, AD-10, AD-13). Template auto-retries,
    operator retries, and operator restarts each prepend to the composed dispatch."""
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
    scope = agent_workdir.prompt_scope(ctx)
    prompt = agent_prompt.compose_prompt(
        scope,
        agent_answer.resolved_signal(ctx),
        previous,
        prompt_file_content=prompt_file_content,
        workflow_path=workflow,
    )
    if redispatched(ctx) and (failure := require_env(ctx).verify_failure) is not None:
        # what a fresh dispatch is told when a `verify` row has just sent the Story back
        # (FR-10): once, on this attempt alone — a retry of it reads `redispatched(ctx)` as
        # `False` (context.py's own "nothing is appended twice") and never repeats it.
        clause = agent_prompt.redispatch_clause(scope, failure)
        if clause:
            prompt = f"{clause} {prompt}"
    if retry is not None or (operator_retry(ctx) and operator_mode == "restart"):
        op = str(ctx.resume_signal.payload.get("text", "")) if ctx.resume_signal else ""
        hint = retry.prompt if retry else getattr(agent_tail.retry_of(ctx), "prompt", "")
        # the retry text in front of the dispatch a *new* session has not been told yet; a
        # resumed one was sent the retry prompt alone above. Both texts are the Template's
        # own — the separator is the one thing composed here (Operator decision, 2026-09-27).
        prompt = f"{op or hint} {prompt}" if op or hint else prompt
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
    """The session's next turn: the Operator's own words, except an Answer, which still
    owes FR-18's clause verbatim — `resolved_signal` reads its condition off the archive
    `execute` makes before this prompt is built, session mode included."""
    resolved = agent_answer.resolved_signal(ctx)
    if resolved is not None and resolved.event == agent_answer.ANSWER_EVENT:
        return agent_prompt.answer_clause(ctx.with_resolved, resolved).strip()
    if ctx.resume_signal is not None and (t := str(ctx.resume_signal.payload.get("text", ""))):
        return t
    retry = agent_tail.retry_of(ctx)
    return retry.prompt if retry is not None else ""


register(KIND, AgentExecutor())
