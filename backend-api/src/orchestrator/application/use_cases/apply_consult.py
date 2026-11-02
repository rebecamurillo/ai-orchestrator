"""`apply_consult` (AD-8, AD-22): what `apply_step_result` writes for a consult result, before
any other routing reads it.

- **An offer** (`Consult` with no `outcome`): the row's entry for that stop kind is written
  `due` with the question and the snapshot, `consult` is recorded (actor `machine`), and the
  row is requeued through `retry`'s own `error → queued` pair. `retry_count` is not touched:
  a consult is not a retry of the Template's. An entry the verify offer already wrote
  (`verify_consult.py`: block and park path, no snapshot) keeps those keys.
- **An answer**: the entry reads `answer` with `answered_by` (the consult attempt), the
  answer is recorded as `senior_answer` (actor `senior`) with payload `{mode: session, text,
  kind}`, `text` being the consult's own `answer` clause, and the row is requeued. The next
  `agent` attempt finds that record as its `resume_signal` (`walk_context.py`).
- **An answer approving test files** (AD-17's 2026-11-02 amendment) first extends
  `run.accepted_paths`, without duplicates, and records `senior_accept` (actor `senior`), so
  the stop records show who accepted. Run-wide, as the Operator's `continue` is.
- **A `verify_failed` answer** is a diagnosis, not a message into a session (AD-10): it is
  recorded with no `mode`, and the requeue counts as one further redispatch on
  `redispatch_count`, so the next failure finds the bound still used up and parks.
- **Anything else** marks the entry and returns `None`: the result carries its own park.

The Run never leaves `running` here and nothing is announced: no person is waiting yet.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.rules import consult as rules
from orchestrator.application.rules.signals import FILES_KEY
from orchestrator.application.use_cases.writers import (
    Entry,
    WriterPorts,
    record,
    set_row,
    set_run,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import StepStatus, step_transition
from orchestrator.domain.values import Consult, StepResult

#: The session delivery a `senior_answer` asks for, in the shape `signal_run` writes.
SESSION = "session"

ACCEPTED = "accepted by the senior: {files}"
REASON_KEY = "reason"


def attempt_status(result: StepResult) -> StepStatus:
    """The status the consult attempt closes with. A `verify_failed` consult that came to a
    park returns its target row to `done` (`result.status`), but the attempt itself did not
    succeed: it closes `error`, the status of the stop it could not clear."""
    failed_closed = result.consult is not None and result.consult.kind == rules.VERIFY_FAILED
    return "error" if failed_closed and result.park is not None else result.status


def apply_consult(
    ports: WriterPorts, run: Run, row: StepRun, result: StepResult, attempt: Attempt | None
) -> Run | None:
    """The Run once a consult result is applied, or `None` when routing is not done."""
    found = result.consult
    if found is None:
        return None
    attempt_n = attempt.n if attempt is not None else None
    if found.outcome is None:
        _offered(ports, run, row, found, attempt_n)
        return run
    entry = {
        key: value
        for key, value in row.consults.get(found.kind, {}).items()
        if key != rules.ORPHAN_PGID_KEY
    }
    entry[rules.STATE_KEY] = found.outcome
    if found.outcome != rules.ANSWER or result.park is not None:
        set_row(ports, row, consults={**row.consults, found.kind: entry})
        return None
    entry[rules.ANSWERED_BY_KEY] = attempt_n
    if found.approved_files:
        run = _accept(ports, run, row, found, attempt_n)
    text = rules.answer_text(row.with_resolved, found.question, found.answer, entry)
    payload = {rules.TEXT_KEY: text, rules.KIND_KEY: found.kind}
    counted: dict[str, Any] = {}
    if found.kind == rules.VERIFY_FAILED:
        counted["redispatch_count"] = row.redispatch_count + 1
    else:
        payload["mode"] = SESSION
    record(
        ports,
        run,
        Entry(
            event="senior_answer",
            actor="senior",
            path=row.path,
            text=found.answer,
            attempt_n=attempt_n,
            payload=payload,
        ),
    )
    _requeue(ports, row, {**row.consults, found.kind: entry}, counted)
    return run


def _accept(
    ports: WriterPorts, run: Run, row: StepRun, found: Consult, attempt_n: int | None
) -> Run:
    files = list(dict.fromkeys(found.approved_files))
    added = tuple(path for path in files if path not in run.accepted_paths)
    updated = set_run(ports, run, accepted_paths=(*run.accepted_paths, *added))
    text = ACCEPTED.format(files=", ".join(files))
    record(
        ports,
        updated,
        Entry(
            event=rules.ACCEPT_EVENT,
            actor="senior",
            path=row.path,
            text=f"{text} · {found.reason}" if found.reason else text,
            attempt_n=attempt_n,
            payload={FILES_KEY: files, REASON_KEY: found.reason, rules.KIND_KEY: found.kind},
        ),
    )
    return updated


def _offered(
    ports: WriterPorts, run: Run, row: StepRun, found: Consult, attempt_n: int | None
) -> None:
    entry = {
        **row.consults.get(found.kind, {}),
        rules.STATE_KEY: rules.DUE,
        rules.QUESTION_KEY: found.question,
        rules.SNAPSHOT_KEY: dict(found.snapshot),
    }
    record(
        ports,
        run,
        Entry(
            event="consult",
            actor="machine",
            path=row.path,
            text=found.question,
            attempt_n=attempt_n,
            payload={rules.KIND_KEY: found.kind},
        ),
    )
    _requeue(ports, row, {**row.consults, found.kind: entry}, {})


def _requeue(
    ports: WriterPorts, row: StepRun, consults: dict[str, Any], counted: dict[str, Any]
) -> None:
    set_row(ports, row, status=step_transition(row.status, "retry"), consults=consults, **counted)
