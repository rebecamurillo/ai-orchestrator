"""The `agent` kind: preparing a worktree for a coding agent, and dispatching one (AD-9,
AD-10, AD-14, FR-14).

**AD-9's side-effect order is the shape of `execute`, verbatim**: orphan control, WIP
commit, the orchestrator's own writes, prepare commit, `start_sha`, prompt, dispatch,
`mark_finished`. The harness lookup runs first, being a pure read: a row naming a harness
this instance lacks must park without leaving a commit behind.

**Three writes, three units of work** (AD-8): `mark_started` before the process exists, the
`pgid` update between `Harness.start` and `Harness.wait`, `mark_finished` after it exits.
The middle one is why the `Harness` port has two halves. Nothing here writes a row, a Run
or a status.

**Orphan control is what makes a restart safe** (AD-14, FR-12): a previous attempt with a
`pgid` and no `end_sha` is a harness a dead backend left running — its group is killed, the
index lock awaited, and only then is it closed `error` · `interrupted`. The discriminator
cannot be `ended_at`: `start_attempt` (`_open_the_row`) already stamps that on an attempt
it finds open after a restart, which is the very case this guards, while `end_sha` is
written only by `_finish` — so it alone means "the dispatch came back".

**The harness receives exactly what `HarnessEnv` returned** (AD-5, AD-10), and **`_tail` is
a stub** whose `done` means "observed", never "verified" — the row's gate is `liveness`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import structlog

from orchestrator.application.steps.context import (
    StepContext,
    log_path,
    require_attempt_writes,
    require_cwd,
    require_env,
    require_harness_env,
    require_harnesses,
    require_process,
    require_run,
    require_workspace,
)
from orchestrator.application.steps.registry import register
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
from orchestrator.domain.ports.harness import Harness, HarnessResult
from orchestrator.domain.ports.repositories import AttemptRepository
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

#: The two commits this module makes, and the document it writes between them.
WIP_MESSAGE = "wip: story {id} attempt {n} (interrupted)"
PREPARE_MESSAGE = "orchestrator: prepare story {id} attempt {n}"
CONTEXT_FILE = "project-context.md"
CONTEXT_HEADING = "## Context files"
CONTEXT_MISSING = "context path missing: {path}"

#: The reasons this row leaves, and what an interrupted attempt carries instead of one.
UNKNOWN_HARNESS = "harness misconfigured: unknown harness {name}"
TIMED_OUT = "timeout {path} after {n} min"
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
    """One dispatch, decided before the span opens: the two calls share these four facts."""

    harness: Harness
    attempt: Attempt
    prompt: str
    session_id: str


class AgentExecutor:
    """Prepare the worktree, dispatch the harness, record the attempt. Decide nothing."""

    def execute(self, ctx: StepContext) -> StepResult:
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
    """What the harness is asked, from the row the planner resolved (FR-14, AD-7).

    Four pieces, in order: the dispatch sentence, what the Template bound as `prompt_extra`,
    the halt a spec checkpoint asks for, and the Operator's answer when one resumed this row.
    The halt is gated on `resume_signal is None` because that is exactly "a first dispatch or
    a re-plan": a `retry` never reaches this function, and a resume must not halt twice.
    """
    parts = [
        DISPATCH.format(
            skill=_text(with_resolved, SKILL_KEY),
            spec_folder=_text(with_resolved, SPEC_FOLDER_KEY),
            story_id=_text(with_resolved, STORY_ID_KEY),
        )
    ]
    extra = _text(with_resolved, PROMPT_EXTRA_KEY)
    if extra:
        parts.append(f" {extra}")
    if with_resolved.get(SPEC_CHECKPOINT_KEY) and resume_signal is None:
        parts.append(HALT)
    if resume_signal is not None and resume_signal.event == ANSWER_EVENT:
        parts.append(
            ANSWER.format(
                condition=resume_signal.payload.get(CONDITION_KEY, ""),
                answer=resume_signal.payload.get(ANSWER_KEY, ""),
            )
        )
    return "".join(parts)


def _harness(ctx: StepContext) -> Harness | StepResult:
    """The adapter this row's `harness:` names, or the park an unknown name is."""
    name = _text(ctx.with_resolved, HARNESS_KEY)
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
    """Kill whatever the last attempt left running, then close it (AD-14, FR-12) — a
    `pgid` and no `end_sha` is "started and never came back"; see the module docstring."""
    previous = ctx.previous_attempt
    if previous is None or previous.pgid is None or previous.end_sha is not None:
        return
    require_process(ctx).kill_group(previous.pgid)
    _await_unlock(ctx)
    closed = previous.model_copy(
        update={"status": "error", "ended_at": ctx.ports.clock.now(), "output_ref": INTERRUPTED}
    )
    _committed(ctx, lambda attempts: attempts.mark_finished(closed))


def _await_unlock(ctx: StepContext) -> None:
    """Poll `.git/index.lock` until git clears it, or until the deadline (AD-14)."""
    workspace = require_workspace(ctx, ctx.cwd)
    waited = 0.0
    while waited < LOCK_TIMEOUT_SECONDS and workspace.exists(INDEX_LOCK):
        ctx.ports.clock.sleep(LOCK_POLL_SECONDS)
        waited += LOCK_POLL_SECONDS


def _wip_commit(ctx: StepContext) -> None:
    """Commit what an interrupted attempt left; a clean tree gets no commit (AD-9)."""
    worktree = require_cwd(ctx)
    git = ctx.ports.git
    if not git.status(worktree).strip():
        return
    git.stage(worktree)
    git.commit(worktree, WIP_MESSAGE.format(id=_story_id(ctx), n=ctx.attempt.n))


def _prepare_writes(ctx: StepContext) -> None:
    """The orchestrator's write into the worktree, and the commit that records it."""
    _prepare_commit(ctx, _context_document(ctx))


def _context_document(ctx: StepContext) -> str | None:
    """`{spec_folder}/project-context.md`, or `None` when the row names no spec folder; a
    path the worktree lacks is logged and left out, and the heading is always written."""
    spec_folder = _text(ctx.with_resolved, SPEC_FOLDER_KEY)
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


def _prepare_commit(ctx: StepContext, target: str | None) -> None:
    """One commit holding exactly the file this row wrote — staged by name, then asked."""
    if target is None:
        return
    worktree = require_cwd(ctx)
    git = ctx.ports.git
    git.stage(worktree, target)
    if not git.status(worktree).strip():
        return
    git.commit(worktree, PREPARE_MESSAGE.format(id=_story_id(ctx), n=ctx.attempt.n))


def _start(ctx: StepContext) -> Attempt:
    """The start half, committed alone, before the process exists: `start_sha` read after
    both commits, `pgid` `None` until `Harness.start` answers (AD-8, AD-14)."""
    start_sha = ctx.ports.git.head_sha(require_cwd(ctx))
    started = ctx.attempt.model_copy(
        update={
            "start_sha": start_sha,
            "frozen_test_files": _frozen_test_files(ctx, start_sha),
            "pgid": None,
            "harness": _text(ctx.with_resolved, HARNESS_KEY),
            "model": (_text(ctx.with_resolved, MODEL_KEY) or None),
        }
    )
    _committed(ctx, lambda attempts: attempts.mark_started(started))
    return started


def _frozen_test_files(ctx: StepContext, start_sha: str | None) -> tuple[str, ...] | None:
    """AD-17's anchors, as the *committed tree* at `start_sha` holds them (AD-17, 5.6).

    Through `Git.list_files` and not off the worktree: 5.6 compares this set against
    `diff_names(start_sha, end_sha)`, and globbing the filesystem would carry directory
    entries and untracked files no commit range can name. Skipped only for an attempt whose
    predecessor actually *reached* `start_sha` (AD-17's "lowest-`n` attempt that has a
    `start_sha`"), so a first attempt that parked in prepare leaves the freezing to the next.
    """
    previous = ctx.previous_attempt
    if start_sha is None or (previous is not None and previous.start_sha is not None):
        return None
    globs = require_env(ctx).test_globs
    tree = ctx.ports.git.list_files(require_cwd(ctx), start_sha, WHOLE_TREE)
    return tuple(sorted(p for p in tree if any(PurePosixPath(p).full_match(g) for g in globs)))


def _dispatch(ctx: StepContext, harness: Harness, attempt: Attempt) -> StepResult:
    """Dispatch inside the attempt's span; an unwired tracer degrades to `""` (AD-11)."""
    dispatch = _Dispatch(
        harness=harness,
        attempt=attempt,
        prompt=compose_prompt(ctx.with_resolved, ctx.resume_signal, ctx.previous_attempt),
        session_id=str(new_id()),
    )
    tracer = ctx.ports.tracer
    if tracer is None:
        return _run(ctx, dispatch, "")
    with tracer.attempt_span(require_run(ctx), ctx.row, attempt) as span:
        return _run(ctx, dispatch, span.traceparent)


def _run(ctx: StepContext, dispatch: _Dispatch, traceparent: str) -> StepResult:
    """Start the harness, commit its group, then wait for it — AD-14's order, exactly."""
    env = require_env(ctx)
    run = require_run(ctx)
    timeout_min = ctx.with_resolved.get(TIMEOUT_KEY) or DEFAULT_TIMEOUT_MIN
    handle = dispatch.harness.start(
        cwd=require_cwd(ctx),
        prompt=dispatch.prompt,
        env=require_harness_env(ctx)(
            dispatch.attempt,
            run=run,
            project_slug=env.project_slug,
            project_env=env.project.env_vars,
            log_content=env.project.log_prompt_content,
            story_id=_story_id(ctx) or None,
            traceparent=traceparent,
        ),
        model=(_text(ctx.with_resolved, MODEL_KEY) or None),
        session_id=dispatch.session_id,
        budget_usd_remaining=run.budget_usd - run.spend_usd,
        timeout_min=timeout_min,
        log_path=log_path(ctx),
    )
    running = dispatch.attempt.model_copy(
        # the session id travels with the group: a backend that dies here must leave behind
        # an attempt FR-21 can still write a `resume_command` for
        update={"pgid": handle.pgid, "session_id": handle.session_id}
    )
    try:
        _committed(ctx, lambda attempts: attempts.update(running))
    except BaseException:
        # this frame is the only place holding the handle, so a write that fails between
        # `start` and `wait` would orphan the process the adapter's own guard never sees
        require_process(ctx).kill_group(handle.pgid)
        raise
    return _finish(ctx, running, dispatch.harness.wait(handle), timeout_min)


def _finish(
    ctx: StepContext, attempt: Attempt, result: HarnessResult, timeout_min: float
) -> StepResult:
    """Record what the harness did, then say what the row reached; `mark_finished` runs
    first, so a killed attempt is as fully recorded as one that exited cleanly (AD-8)."""
    finished = attempt.model_copy(
        update={
            "ended_at": ctx.ports.clock.now(),
            "end_sha": ctx.ports.git.head_sha(require_cwd(ctx)),
            "exit_code": result.exit_code,
            "session_id": result.session_id,
            "log_path": str(result.log_path),
            **_usage(result),
        }
    )
    _committed(ctx, lambda attempts: attempts.mark_finished(finished))
    if result.timed_out:
        reason = TIMED_OUT.format(path=ctx.row.path, n=timeout_min)
        return StepResult(
            status="error",
            gate=ctx.row.gate,
            output_ref=str(result.log_path),
            reason=reason,
            park=Park(kind="timeout", reason=reason, path=ctx.row.path),
        )
    return _tail(ctx, finished, result)


def _tail(ctx: StepContext, attempt: Attempt, result: HarnessResult) -> StepResult:
    """What the dispatch reached — a stub whose `done` means "5.5 will decide". 5.5 reads
    `expect`/`retry`, 5.6 the range, 5.7 the usage: all three already arguments here."""
    return StepResult(status="done", gate=ctx.row.gate, output_ref=str(result.log_path))


def _usage(result: HarnessResult) -> dict[str, Any]:
    """The harness's figures, or nothing — never zeroes read back as measured (AD-11)."""
    usage = result.usage
    if usage is None:
        return {}
    return {
        "tokens_in": usage.tokens_in,
        "tokens_out": usage.tokens_out,
        "cost_usd": usage.cost_usd,
        "cost_provisional": True,
    }


def _committed(ctx: StepContext, write: Callable[[AttemptRepository], None]) -> None:
    """One attempt write, in its own scope and transaction; `AttemptRepository` only (AD-8)."""
    with require_attempt_writes(ctx)() as writers, writers.uow:
        write(writers.attempts)
        writers.uow.commit()


def _story_id(ctx: StepContext) -> str:
    """The Story this row works on, flattened onto the row by the planner (AD-7)."""
    return _text(ctx.with_resolved, STORY_ID_KEY)


def _text(resolved: Mapping[str, Any], key: str) -> str:
    """One resolved key as a string; an absent, null or empty value is `""` either way."""
    return str(resolved.get(key) or "").strip()


register(KIND, AgentExecutor())
