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
files answers a `protected_path` park (AD-17): the work is already in the worktree, so
`agent_tail.re_check` re-runs the check and the routing over the previous attempt and
`execute` returns that — before the orphan control, before the WIP commit, before anything
here would put a commit of its own in front of the range about to be read.

**Three re-dispatches reach this module and are not the same dispatch** (AD-9, AD-13): the
Template's own `retry`, which resumes the session or prepends its prompt to a fresh one; a
person's *Retry* from a stop, which archives every extra Story file an ambiguity left before
anything reads the glob again (AD-13); a `verify` redispatch, which hands
the agent its file back at `in-progress` with a `## Verify Failure` section (FR-10).
`context.retrying`, `context.operator_retry` and `context.redispatched` tell them apart, off
`StepContext` alone.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import structlog

from orchestrator.application.steps import agent_tail
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
    PROMPT_EXTRA_KEY,
    SPEC_CHECKPOINT_KEY,
    SPEC_FOLDER_KEY,
    STORY_ID_KEY,
)
from orchestrator.application.templates.rows import TIMEOUT_KEY
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
SKILL_KEY = "skill"
#: The `answer` signal's payload, as `signal_run` stored it.
ANSWER_EVENT = "answer"
CONDITION_KEY = "condition"
ANSWER_KEY = "answer"

#: The prompt, in the pieces FR-14 pins. Asserted verbatim by the prompt tests.
DISPATCH = (
    "Run the skill {skill} in folder+id dispatch mode: "
    "spec folder {spec_folder}, story id {story_id}."
)
HALT = " Halt after planning."
ANSWER = ' Answer from the operator to the blocking condition "{condition}": {answer}'
#: How a retry prompt reaches a *new* session: in front of the dispatch sentence the session
#: has not been told yet. A resumed one is sent the retry prompt alone.
RETRY_PROMPT = "{retry} {dispatch}"

#: The two commits this module makes, and the documents it writes between them.
WIP_MESSAGE = "wip: story {id} attempt {n} (interrupted)"
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

#: Every path at a ref, as a pathspec. Not `""`: git refuses that by name and the adapter
#: reports a refusal as `()`, so AD-17's set would come back empty and nothing would fail.
WHOLE_TREE = "."

#: `KIND_META["agent"].timeout_default_min` — what a row carrying no resolved timeout gets.
DEFAULT_TIMEOUT_MIN = 90


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
        _orphan_control(ctx)
        _wip_commit(ctx)
        _prepare_writes(ctx)
        return _dispatch(ctx, found, _start(ctx))


def compose_prompt(
    with_resolved: Mapping[str, Any],
    resume_signal: GateRecord | None,
    previous_attempt: Attempt | None,
) -> str:
    """What the harness is asked, from the row the planner resolved (FR-14, AD-7): the
    dispatch sentence, the Template's `prompt_extra`, the halt a spec checkpoint asks for,
    and the Operator's answer when one resumed this row. The halt is gated on
    `resume_signal is None` because that is exactly "a first dispatch or a re-plan": a
    `retry` never reaches this function, and a resume must not halt twice."""
    parts = [
        DISPATCH.format(
            skill=resolved_text(with_resolved, SKILL_KEY),
            spec_folder=resolved_text(with_resolved, SPEC_FOLDER_KEY),
            story_id=resolved_text(with_resolved, STORY_ID_KEY),
        )
    ]
    payload = resume_signal.payload if resume_signal is not None else {}
    extra = resolved_text(with_resolved, PROMPT_EXTRA_KEY)
    if extra:
        parts.append(f" {extra}")
    if with_resolved.get(SPEC_CHECKPOINT_KEY) and resume_signal is None:
        parts.append(HALT)
    if resume_signal is not None and resume_signal.event == ANSWER_EVENT:
        condition, answer = payload.get(CONDITION_KEY, ""), payload.get(ANSWER_KEY, "")
        parts.append(ANSWER.format(condition=condition, answer=answer))
    return "".join(parts)


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
    """Kill whatever the last attempt left running, wait for git to clear its own crash lock,
    then close the attempt (AD-14, FR-12). The wait is bounded and never raises: the row goes
    on either way, and the commit that follows reports the lock if it is still there."""
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


def _wip_commit(ctx: StepContext) -> None:
    """Commit what an interrupted attempt left; a clean tree gets no commit (AD-9)."""
    worktree = require_cwd(ctx)
    git = ctx.ports.git
    if not git.status(worktree).strip():
        return
    git.stage(worktree)
    git.commit(worktree, WIP_MESSAGE.format(id=_text(ctx, STORY_ID_KEY), n=ctx.attempt.n))


def _prepare_writes(ctx: StepContext) -> None:
    """The orchestrator's writes into the worktree, and the one commit holding exactly them.

    The archive runs first: everything after it reads the glob it leaves behind. Its renames
    are staged alongside the files written, because they are this row's writes too — an
    unstaged move would still be in the tree at `start_sha` and 5.6 would read it as the
    agent's (AD-17, FR-31), and it would dirty the whole-tree commit guard while leaving the
    index empty. Files are staged by name and the tree asked afterwards, so unchanged bytes
    leave no empty commit.
    """
    moved = agent_tail.archive_ambiguous(ctx)
    written = (_context_document(ctx), _verify_failure(ctx))
    targets = [*moved, *(target for target in written if target is not None)]
    if not targets:
        return
    worktree = require_cwd(ctx)
    git = ctx.ports.git
    for target in targets:
        git.stage(worktree, target)
    if not git.status(worktree).strip():
        return
    git.commit(worktree, PREPARE_MESSAGE.format(id=_text(ctx, STORY_ID_KEY), n=ctx.attempt.n))


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
    """The start half, committed alone, before the process exists: `start_sha` after both
    commits, `pgid` `None` until the harness answers (AD-8, AD-14)."""
    start_sha = ctx.ports.git.head_sha(require_cwd(ctx))
    started = ctx.attempt.model_copy(
        update={
            "start_sha": start_sha,
            "frozen_test_files": _frozen_test_files(ctx, start_sha),
            "pgid": None,
            "harness": _text(ctx, HARNESS_KEY),
            "model": (_text(ctx, MODEL_KEY) or None),
        }
    )
    committed(ctx, lambda attempts: attempts.mark_started(started))
    return started


def _frozen_test_files(ctx: StepContext, start_sha: str | None) -> tuple[str, ...] | None:
    """AD-17's anchors, as the *committed tree* at `start_sha` holds them (AD-17, 5.6).
    Through `Git.list_files` and not off the worktree: 5.6 compares this set against
    `diff_names(start_sha, end_sha)`, and globbing the filesystem would carry directory
    entries and untracked files no commit range can name. Skipped only for an attempt whose
    predecessor actually *reached* `start_sha`."""
    previous = ctx.previous_attempt
    if start_sha is None or (previous is not None and previous.start_sha is not None):
        return None
    globs = require_env(ctx).test_globs
    tree = ctx.ports.git.list_files(require_cwd(ctx), start_sha, WHOLE_TREE)
    return tuple(sorted(p for p in tree if any(PurePosixPath(p).full_match(g) for g in globs)))


def _dispatch(ctx: StepContext, harness: Harness, attempt: Attempt) -> StepResult:
    """Dispatch inside the attempt's span; an unwired tracer degrades to `""` (AD-11)."""
    dispatch = _planned(ctx, harness, attempt)
    tracer = ctx.ports.tracer
    if tracer is None:
        return _run(ctx, dispatch, "")
    with tracer.attempt_span(require_run(ctx), ctx.row, attempt) as span:
        return _run(ctx, dispatch, span.traceparent)


def _planned(ctx: StepContext, harness: Harness, attempt: Attempt) -> _Dispatch:
    """Which of the three dispatches this is, and what it carries (FR-16, AD-10).
    `compose_prompt` never sees a retry prompt: a resumed session already holds the context
    that sentence would repeat, while a session that cannot be resumed — the contract said
    not to, the harness cannot, or the last attempt recorded none — is a new one, which
    needs the sentence and gets the retry prompt in front of it."""
    previous = ctx.previous_attempt
    retry = agent_tail.retry_of(ctx) if retrying(ctx) else None
    session, resumable = str(new_id()), previous.session_id if previous is not None else None
    if retry is not None and retry.resume_session and harness.capabilities.resume and resumable:
        return _Dispatch(harness, attempt, retry.prompt, session, resumable)
    prompt = compose_prompt(ctx.with_resolved, ctx.resume_signal, previous)
    if retry is not None:
        prompt = RETRY_PROMPT.format(retry=retry.prompt, dispatch=prompt)
    return _Dispatch(harness, attempt, prompt, session)


def _run(ctx: StepContext, dispatch: _Dispatch, traceparent: str) -> StepResult:
    """Start the harness, commit its group, then wait for it — AD-14's order, exactly. A
    resumed session skips the middle write: `Harness.resume` is one call, so no handle sits
    between two halves for a dead backend to lose."""
    run, environment = require_run(ctx), require_env(ctx)
    timeout_min = ctx.with_resolved.get(TIMEOUT_KEY) or DEFAULT_TIMEOUT_MIN
    env = require_harness_env(ctx)(
        dispatch.attempt,
        run=run,
        project_slug=environment.project_slug,
        project_env=environment.project.env_vars,
        log_content=environment.project.log_prompt_content,
        story_id=_text(ctx, STORY_ID_KEY) or None,
        traceparent=traceparent,
    )
    if dispatch.resume_id is not None:
        resumed = dispatch.harness.resume(
            cwd=require_cwd(ctx),
            session_id=dispatch.resume_id,
            message=dispatch.prompt,
            env=env,
            timeout_min=timeout_min,
            log_path=log_path(ctx),
        )
        return agent_tail.finish(ctx, dispatch.attempt, resumed, timeout_min)
    handle = dispatch.harness.start(
        cwd=require_cwd(ctx),
        prompt=dispatch.prompt,
        env=env,
        model=(_text(ctx, MODEL_KEY) or None),
        session_id=dispatch.session_id,
        budget_usd_remaining=run.budget_usd - run.spend_usd,
        timeout_min=timeout_min,
        log_path=log_path(ctx),
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
    return agent_tail.finish(ctx, running, dispatch.harness.wait(handle), timeout_min)


def _text(ctx: StepContext, key: str) -> str:
    """One of this row's resolved keys as a string — `STORY_ID_KEY` is the Story it works
    on, flattened onto the row by the planner (AD-7)."""
    return resolved_text(ctx.with_resolved, key)


register(KIND, AgentExecutor())
