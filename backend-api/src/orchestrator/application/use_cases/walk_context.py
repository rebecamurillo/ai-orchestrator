"""AD-9's `StepContext` for the row about to run, read out of the Run the walker stands in.

**A verify failure and a frame's anchors are resolved here for the same reason
`frame_start_sha` is**: a row a `verify` step sent back needs facts about a *different* row
(FR-10), AD-17's rule needs every row of the Story frame, and AD-9 closes `StepContext`'s
field list. Read once, here — the only place holding both the rows and the repositories —
and handed over as frozen values on `RunEnvironment`/`StepPorts` (AD-8).

**`resume_signal` is the Operator's record, or else the senior's** (AD-22): a `senior_answer`
`rules/consult.py::delivers` still owes the row. It travels as a real record so the `agent`
executor's session path reads it exactly as it reads an Operator's `answer {mode: session}`.
A `verify_failed` diagnosis is the exception: it rides on `VerifyFailure.diagnosis` instead, so
it reaches a fresh redispatch and never resumes the row's old session (AD-10).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from uuid import UUID

from orchestrator.application.rules.consult import delivers, diagnosis
from orchestrator.application.steps import WORKDIR_KEY, StepContext, StepPorts
from orchestrator.application.steps.verify_failure import VerifyFailure
from orchestrator.application.templates.plan_model import ON_FAIL_KEY, REDISPATCH_TARGET_SEQ
from orchestrator.application.templates.rows import COMMAND_KEY
from orchestrator.application.use_cases.walk_frame import (
    WalkFrame,
    frame_anchors,
    frame_start_sha,
    read_frame,
)
from orchestrator.application.use_cases.writers import WriterPorts, require_row
from orchestrator.domain.entities.attempt import Attempt, agent_attempts
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import NotFound
from orchestrator.domain.statuses import GateEvent

#: How much of a failed `verify` row's log the Story file is handed back (FR-10). Enough to
#: show what failed, bounded so a prepare commit never carries a whole build log.
VERIFY_LOG_LINES = 200


def context(
    writers: WriterPorts,
    step: StepPorts,
    run: Run,
    seq: int,
    resume_event: GateEvent | None,
) -> StepContext:
    """AD-9's own field list, read out of the Run the walker is standing in."""
    run_id = run.id
    row = require_row(writers, run_id, seq)
    attempts = writers.attempts.list_for_row(row.id)
    if not attempts:
        raise NotFound(f"no attempt on step {seq} of run {run_id}")
    frame = read_frame(writers, run_id, row)
    return StepContext(
        row=row,
        with_resolved=row.with_resolved,
        cwd=run.worktree_path,
        frame_start_sha=frame_start_sha(frame.attempts),
        previous_attempt=next(reversed(agent_attempts(attempts[:-1])), None),
        attempt=attempts[-1],
        resume_signal=_resume_signal(writers, row, attempts, resume_event),
        ports=_step_ports(writers, step, run, row, frame, attempts=attempts),
    )


def _step_ports(  # noqa: PLR0913 — the row, its frame and its attempts, each read once above
    writers: WriterPorts,
    step: StepPorts,
    run: Run,
    row: StepRun,
    frame: WalkFrame,
    *,
    attempts: list[Attempt],
) -> StepPorts:
    """The executors' ports, plus whatever this row alone needs resolving (FR-10, AD-17).

    A walker that resolved no environment is handed over unchanged: there is nowhere to put a
    frame's facts, and the executor refuses with the wiring error `require_env` names.

    **Only a row inside a Story frame is given the rule.** AD-17 is frame-scoped: its frozen
    test set is that frame's first attempt's, and outside a frame there is no agent range at
    all — so all that would be left of the check is "anything staged whose basename is
    `AGENTS.md`". A `bmad.install` row stages exactly that, written by the
    orchestrator, and would park a Run on the system's own file.
    """
    environment = step.run_env
    if environment is None:
        return step
    environment = replace(
        environment,
        verify_failure=_verify_failure(writers, step, run.id, row),
        story_baseline_sha=_story_baseline_sha(row, attempts),
    )
    if row.frame is None:
        return replace(step, run_env=environment)
    rule = frame_anchors(step.git, run, environment, frame, row)
    return replace(step, run_env=replace(environment, anchors=rule.anchors), protected_paths=rule)


def _story_baseline_sha(row: StepRun, attempts: list[Attempt]) -> str | None:
    """The root-tree start SHA of the row's lowest-`n` `agent` attempt that recorded one."""
    in_workdir = bool(row.with_resolved.get(WORKDIR_KEY))
    for attempt in sorted(agent_attempts(attempts), key=lambda a: a.n):
        sha = attempt.root_start_sha if in_workdir else attempt.start_sha
        if sha is not None:
            return sha
    return None


def _verify_failure(
    writers: WriterPorts, step: StepPorts, run_id: UUID, row: StepRun
) -> VerifyFailure | None:
    """Why the `verify` row redispatched to this one failed, or `None` when none did.

    The target is matched on `seq` rather than on a kind: `on_fail: {redispatch: …}` is the
    only thing that sends a Run backwards (AD-9), and the planner already resolved it to
    this row's number (`templates/plan_model.py`). A `verify` row that never recorded an
    attempt still names its command — the Operator can read that even with no code to show.
    """
    if row.redispatch_count == 0:
        return None
    sender = next(
        (entry for entry in writers.steps.list_for_run(run_id) if redispatches_to(entry, row.seq)),
        None,
    )
    if sender is None:
        return None
    attempts = writers.attempts.list_for_row(sender.id)
    latest = attempts[-1] if attempts else None
    reader = step.logs
    tail = reader.tail(latest.log_path, VERIFY_LOG_LINES) if reader and latest else []
    owed = diagnosis(
        row, writers.attempts.list_for_row(row.id), writers.records.list_for_run(run_id)
    )
    return VerifyFailure(
        command=str(sender.with_resolved.get(COMMAND_KEY) or ""),
        exit_code=latest.exit_code if latest is not None else None,
        log_tail=tuple(tail),
        diagnosis=owed,
    )


def redispatches_to(row: StepRun, seq: int) -> bool:
    """Whether this row's own `on_fail` is a redispatch aimed at `seq` (AD-9)."""
    action = row.with_resolved.get(ON_FAIL_KEY)
    return isinstance(action, Mapping) and action.get(REDISPATCH_TARGET_SEQ) == seq


def _resume_signal(
    writers: WriterPorts,
    row: StepRun,
    attempts: list[Attempt],
    resume_event: GateEvent | None,
) -> GateRecord | None:
    """The record `signal_run` wrote for the signal that resumed this row (AD-9), or the
    senior's answer still owed to it (AD-22)."""
    if resume_event is not None:
        records = writers.records.list_for_run(row.run_id)
        found = next((line for line in reversed(records) if line.event == resume_event), None)
        if found is not None:
            return found
    if not row.consults:
        return None
    return delivers(row, attempts, writers.records.list_for_run(row.run_id))
