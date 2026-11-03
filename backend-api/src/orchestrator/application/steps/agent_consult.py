"""The `agent` kind's consult (AD-21, AD-22): the offer at a `blocked` or `protected_path`
stop, and the consult attempt that answers it.

**The offer** (`offer`) runs at the end of the agent's own tail. A `blocked` park on a row
that declares `consult {on: [blocked]}`, has not consulted on that kind, and stopped on an
attempt that can be resumed (a recorded `session_id`, a harness with `resume`) comes back as
`error` plus `Consult{kind, question, snapshot}` instead of the park; `apply_step_result`
records it and requeues the row. Every other result passes through unchanged.

**A `protected_path` hit** (story 1-8) is offered on a row declaring that stop when no hit
is a document; nothing is resumed, so no session is needed. The offer records the stopped
attempt's spend first and carries the hits payload, which every fail-closed park carries
again, with status `error`, so the Operator's diff view and `continue` work unchanged. Its
consult writes the hits' diff beside the decision file, and only `accept` is delivered.

**The consult attempt** (`run`) is the row's next attempt, opened with `role = consult` by
`start_attempt`. Its order is fixed: kill the orphan a dead backend left; check the budget;
look up the harness; write the folder's `.gitignore`; clear the decision path and copy the
story baseline (`agent_consult_review`); fill the prompt; then `mark_started`
(no start SHAs: a consult is outside every AD-17 range) and the senior's own process
(`agent_consult_senior`). Only then are the trees checked against the offer's snapshot and
the decision read through the Workspace port (`rules/consult.py`).

**A `verify_failed` consult** (story 1-6) is the same attempt on the redispatch target. It is
offered by `use_cases/verify_consult.py`, not by `offer`; it runs on the block its entry
carries, and is told the failing command, exit code and output tail and the log of the
target's last `agent` attempt. Its stop parks on the verify row, and the target returns to
`done`.

**It fails closed, always.** Every outcome but an answer parks the original `blocked` stop,
with the senior's reason added when it gave one, and every exception is caught into the
same park: a stop the Operator can read and answer, never an `internal` one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import structlog

from orchestrator.application.rules import budget, consult
from orchestrator.application.steps import (
    agent_consult_review,
    agent_consult_senior,
    agent_consult_tree,
    agent_env,
    agent_tail,
    agent_workdir,
)
from orchestrator.application.steps.context import (
    StepContext,
    committed,
    require_env,
    require_harnesses,
    require_process,
    require_run,
    require_workspace,
    resolved_text,
)
from orchestrator.application.story_file import NO_EXIT_CODE
from orchestrator.application.templates.agent_row import SPEC_FOLDER_KEY, STORY_ID_KEY
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.statuses import AttemptRole, ParkKind, StepStatus
from orchestrator.domain.values import Consult, ConsultOutcome, Park, StepResult

log = structlog.get_logger(__name__)

CONSULT_ROLE: AttemptRole = "consult"
BLOCKED: ParkKind = "blocked"
PROTECTED_PATH: ParkKind = consult.PROTECTED_PATH
HARNESS_KEY = "harness"

#: The reasons a consult leaves on the row and the park. `{question}` is the stop's own.
OFFERED = "consult: {question}"
ANSWERED = "senior answered: {line}"
ACCEPTED = "senior accepted: {files}"
PATHS = ", "
ESCALATED = "{question} · senior: {reason}"
ANSWERED_OVER_BUDGET = "{question} · senior answered: {line}"
#: `FAILED`'s `{why}` for an acceptance whose own spend exhausted the budget.
ACCEPTED_OVER_BUDGET = "senior accepted ({reason}); no remaining budget"
FAILED = "{question} · consult failed: {why}"

#: Why a consult failed closed, as `FAILED`'s `{why}`.
NO_DECISION = "no readable decision"
NO_BUDGET = "no remaining budget"
NOT_DUE = "no consult due"
UNKNOWN_HARNESS = "unknown harness {name}"
EXITED = "senior exit {code}"
STALLED = "senior stalled: no activity for {n} min"
TIMED_OUT = "senior timeout after {n} min"
TREE_CHANGED = "tree changed: {files}"
RAISED = "{name}: {message}"

CONSULT_FAILED = "consult failed"

#: How much of the target's last agent log a `verify_failed` senior is handed.
AGENT_LOG_LINES = 200


def offer(
    ctx: StepContext, attempt: Attempt, final: StepResult, result: HarnessResult | None = None
) -> StepResult:
    """`final`, or the offer it becomes when the stop qualifies (see the module docstring).
    `result` is what the stopped dispatch reported, whose spend a `protected_path` offer
    records first: the hit returns before the tail's own spend is recorded."""
    park = final.park
    if park is None or final.budget_park is not None:
        return final
    if not _qualifies(ctx, attempt, final, park.kind):
        return final
    if not consult.offered(ctx.with_resolved, ctx.row.consults, park.kind):
        return final
    review = park.kind == PROTECTED_PATH
    if review and result is not None:
        spent = agent_tail.record_spend(ctx, attempt, result)
        over = budget.check(spent) if spent is not None else None
        if over is not None:
            return final.model_copy(update={"budget_park": over})
    try:
        snapshot = agent_consult_tree.sweep_and_snapshot(ctx, attempt.n)
    except GitError as error:
        reason = FAILED.format(question=park.reason, why=_git_words(error))
        return final.model_copy(
            update={"reason": reason, "park": park.model_copy(update={"reason": reason})}
        )
    return StepResult(
        status="error",
        gate=final.gate,
        output_ref=final.output_ref,
        reason=OFFERED.format(question=park.reason),
        consult=Consult(
            kind=park.kind,
            question=park.reason,
            snapshot=snapshot,
            hits=dict(final.payload) if review else {},
        ),
    )


def _qualifies(ctx: StepContext, attempt: Attempt, final: StepResult, kind: str) -> bool:
    """A `protected_path` hit on tests only, or a `blocked` stop the agent can resume."""
    if kind == PROTECTED_PATH:
        return agent_consult_review.qualifies(final.payload)
    return final.status == BLOCKED and kind == BLOCKED and _resumable(ctx, attempt)


def _resumable(ctx: StepContext, attempt: Attempt) -> bool:
    harness = require_harnesses(ctx).get(resolved_text(ctx.with_resolved, HARNESS_KEY))
    return attempt.session_id is not None and harness is not None and harness.capabilities.resume


@dataclass(frozen=True)
class _Stop:
    """The stop a consult attempt answers: its kind, its question, and the offer's entry."""

    kind: ParkKind
    question: str
    entry: dict[str, Any]
    #: The senior's block: the entry's own for a stop declared elsewhere, else the row's.
    block: Mapping[str, Any]


def run(ctx: StepContext) -> StepResult:
    """The consult attempt, whole; every failure is the original stop, parked."""
    found = consult.due(ctx.row.consults)
    if found is None:
        return _parked(ctx, _Stop(BLOCKED, ctx.row.reason or "", {}, {}), FAILED, NOT_DUE)
    kind, entry = found
    block = consult.block_of(ctx.with_resolved, entry)
    stop = _Stop(kind, str(entry.get(consult.QUESTION_KEY, "")), dict(entry), block)  # type: ignore[arg-type]
    if consult.SNAPSHOT_KEY not in entry:
        return _snapshotted(ctx, stop)
    try:
        return _consult(ctx, stop)
    except GitError as error:
        return _parked(ctx, stop, FAILED, _git_words(error))
    except Exception as error:
        log.exception(CONSULT_FAILED, path=ctx.row.path, attempt=ctx.attempt.n)
        why = RAISED.format(name=type(error).__name__, message=error)
        return _parked(ctx, stop, FAILED, why)


def _snapshotted(ctx: StepContext, stop: _Stop) -> StepResult:
    """The first attempt of a `verify_failed` consult, whose entry the writer left without a
    snapshot: git work belongs to the executor's step (AD-22), so the sweep and the snapshot
    are taken here and handed back as an offer, which `apply_consult` merges into the entry.
    No senior is dispatched; the row's next attempt is the consult itself.

    Only git's own refusal parks with its words. Any other exception propagates to the
    registry, which parks `internal`, as an offer made in an agent's tail does.
    """
    previous = ctx.previous_attempt
    try:
        snapshot = agent_consult_tree.sweep_and_snapshot(ctx, previous.n if previous else 0)
    except GitError as error:
        return _parked(ctx, stop, FAILED, _git_words(error))
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        reason=OFFERED.format(question=stop.question),
        consult=Consult(kind=stop.kind, question=stop.question, snapshot=snapshot),
    )


def _consult(ctx: StepContext, stop: _Stop) -> StepResult:
    orphan = stop.entry.get(consult.ORPHAN_PGID_KEY)
    if isinstance(orphan, int):
        require_process(ctx).kill_group(orphan)
    remaining = agent_env.remaining(require_run(ctx))
    if remaining is not None and remaining <= 0:
        return _parked(ctx, stop, FAILED, NO_BUDGET)
    block = stop.block
    name = str(block.get(HARNESS_KEY) or "") or resolved_text(ctx.with_resolved, HARNESS_KEY)
    harness = require_harnesses(ctx).get(name)
    if harness is None:
        return _parked(ctx, stop, FAILED, UNKNOWN_HARNESS.format(name=name))
    tree = agent_workdir.tree(ctx)
    workspace = require_workspace(ctx, str(tree))
    workspace.write(consult.IGNORE_FILE, consult.IGNORE_ALL)
    decision = consult.decision_path(ctx.row.seq, ctx.attempt.n)
    agent_consult_review.prepare(ctx, decision)
    unwritten = (
        agent_consult_review.write_diff(ctx, stop.entry) if stop.kind == PROTECTED_PATH else None
    )
    if unwritten is not None:
        return _parked(ctx, stop, FAILED, unwritten)
    prompt = _prompt(ctx, block, stop, str(tree / decision))
    started = ctx.attempt.model_copy(
        update={"pgid": None, "harness": name, "model": str(block.get("model") or "") or None}
    )
    committed(ctx, lambda attempts: attempts.mark_started(started))
    senior = agent_consult_senior.Senior(harness, started, prompt, tree, block)
    result, spent = agent_consult_senior.dispatch(ctx, senior)
    text = agent_consult_review.read_decision(workspace, decision)
    return _with_budget(ctx, stop, _outcome(ctx, stop, result, text), spent)


def _prompt(ctx: StepContext, block: Mapping[str, Any], stop: _Stop, decision: str) -> str:
    """The consult's own `dispatch` clause, filled (`agent_workdir.prompt_scope`'s spelling)."""
    scope = agent_workdir.prompt_scope(ctx)
    prompts = block.get(consult.PROMPTS_KEY) or {}
    return consult.fill(
        str(prompts.get("dispatch", "")),
        {
            "skill": str(block.get("skill", "")),
            "spec_folder": resolved_text(scope, SPEC_FOLDER_KEY),
            "story_id": resolved_text(scope, STORY_ID_KEY),
            "condition": stop.question,
            "decision": decision,
            **_failure(ctx, stop),
        },
    )


def _failure(ctx: StepContext, stop: _Stop) -> dict[str, str]:
    """A `verify_failed` stop's own tokens: the failing command, its exit code and output
    tail as the walker resolved them (`VerifyFailure`), and the tail of the log of the target
    row's last `agent` attempt, read through the `LogReader` port like `{tail}` is: a senior
    is never handed a path under the log volume, which its sandbox may not reach. Empty for
    any other stop."""
    if stop.kind != consult.VERIFY_FAILED:
        return {}
    failure = require_env(ctx).verify_failure
    previous, reader = ctx.previous_attempt, ctx.ports.logs
    lines = reader.tail(previous.log_path, AGENT_LOG_LINES) if previous and reader else []
    facts = {"agent_log": "\n".join(lines)}
    if failure is None:
        return {**facts, "command": "", "code": "", "tail": ""}
    code = NO_EXIT_CODE if failure.exit_code is None else str(failure.exit_code)
    return {**facts, "command": failure.command, "code": code, "tail": "\n".join(failure.log_tail)}


def _outcome(ctx: StepContext, stop: _Stop, result: HarnessResult, text: str | None) -> StepResult:
    """What the senior's exit, the trees and the decision file come to, in that order."""
    log_ref = str(result.log_path)
    files = agent_consult_tree.changed(ctx, stop.entry.get(consult.SNAPSHOT_KEY) or {})
    if files:
        why = TREE_CHANGED.format(files=", ".join(files))
        return _parked(ctx, stop, FAILED, why, log_ref)
    crashed = _crash(ctx, result, stop.block)
    if crashed is not None:
        return _parked(ctx, stop, FAILED, crashed, log_ref)
    decision = consult.parse(text)
    outcome, said = consult.verdict(decision, stop.kind)
    if outcome == consult.ESCALATE:
        template = ESCALATED if said else "{question}"
        return _parked(ctx, stop, template, said, log_ref, outcome="escalate")
    if outcome == consult.FAILED or decision is None:
        return _parked(ctx, stop, FAILED, NO_DECISION, log_ref)
    if outcome == consult.ACCEPT:
        hits = stop.entry.get(consult.HITS_KEY) or {}
        reviewed = agent_consult_review.accepted(stop.question, hits, decision)
    else:
        reviewed = agent_consult_review.answered(ctx, stop.kind, stop.question, decision)
    if isinstance(reviewed, str):
        return _parked(ctx, stop, FAILED, reviewed, log_ref)
    if outcome == consult.ACCEPT:
        line = ACCEPTED.format(files=PATHS.join(reviewed.approved_files))
    else:
        line = ANSWERED.format(line=_first_line(said))
    return StepResult(
        status="error", gate=ctx.row.gate, output_ref=log_ref, reason=line, consult=reviewed
    )


def _crash(ctx: StepContext, result: HarnessResult, block: Mapping[str, Any]) -> str | None:
    if result.stalled:
        return STALLED.format(n=agent_consult_senior.stall_min(ctx))
    if result.timed_out:
        return TIMED_OUT.format(n=block.get("timeout_min"))
    if result.exit_code != 0:
        code = NO_EXIT_CODE if result.exit_code is None else result.exit_code
        return EXITED.format(code=code)
    return None


def _with_budget(ctx: StepContext, stop: _Stop, outcome: StepResult, run: Run | None) -> StepResult:
    """FR-17 over the consult's own spend: the stop it parks gets the `budget` record on top,
    and an answer that exhausted the budget parks instead of being delivered."""
    park = budget.check(run) if run is not None else None
    if park is None:
        return outcome
    if outcome.park is not None:
        return outcome.model_copy(update={"budget_park": park})
    if stop.kind == PROTECTED_PATH:
        said = outcome.consult.reason if outcome.consult is not None else ""
        why = ACCEPTED_OVER_BUDGET.format(reason=said)
        parked = _parked(ctx, stop, FAILED, why, outcome.output_ref, outcome="accept")
        return parked.model_copy(update={"budget_park": park})
    line = _first_line(outcome.consult.answer if outcome.consult is not None else "")
    parked = _parked(ctx, stop, ANSWERED_OVER_BUDGET, line, outcome.output_ref, outcome="answer")
    return parked.model_copy(update={"budget_park": park})


def _parked(  # noqa: PLR0913 — the stop, the sentence, its one value, and what came with it
    ctx: StepContext,
    stop: _Stop,
    template: str,
    value: str,
    output_ref: str | None = None,
    *,
    outcome: ConsultOutcome = "failed",
) -> StepResult:
    """The original stop, parked, its reason carrying what the consult came to.

    A `verify_failed` stop parks on the verify row the offer named, and the target row it
    consulted on goes back to `done`: its work was finished before the gate failed. A
    `protected_path` stop parks `error` with the offer's hits payload, as the hit did."""
    reason = template.format(question=stop.question, why=value, reason=value, line=value)
    review = stop.kind == PROTECTED_PATH
    status: StepStatus = "done" if stop.kind == consult.VERIFY_FAILED else "blocked"
    path = str(stop.entry.get(consult.PARK_PATH_KEY) or ctx.row.path)
    return StepResult(
        status="error" if review else status,
        gate=ctx.row.gate,
        output_ref=output_ref,
        reason=reason,
        park=Park(kind=stop.kind, reason=reason, path=path),
        payload=dict(stop.entry.get(consult.HITS_KEY) or {}) if review else {},
        consult=Consult(kind=stop.kind, question=stop.question, outcome=outcome),
    )


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def _git_words(error: GitError) -> str:
    return error.output.strip() or str(error)
