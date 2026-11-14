"""Gate-record events read as time and as the attempts they created (ARCHITECTURE §5.6).

Waiting on you runs from a park record to the next operator signal or lifecycle record; the
attempts a retry, a redispatch or an operator retry created are found by start time, because
the record names the row, not the attempt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from orchestrator.application.metrics.inputs import AttemptInputs, RunInputs
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.statuses import LIFECYCLE_EVENTS, PARK_KINDS, SIGNAL_KINDS

RETRY_AUTO = "retry_auto"
REDISPATCH = "redispatch"
OPERATOR_RETRY = "operator"
RETRY_KINDS = (RETRY_AUTO, REDISPATCH, OPERATOR_RETRY)
SIGNALLERS = ("operator", "chat")


@dataclass(frozen=True)
class ParkSpan:
    position: int
    kind: str
    path: str | None
    start: datetime
    end: datetime

    @property
    def seconds(self) -> Decimal:
        return Decimal(int((self.end - self.start).total_seconds()))


def park_spans(inputs: RunInputs) -> list[ParkSpan]:
    records = list(inputs.records)
    spans: list[ParkSpan] = []
    for index, record in enumerate(records):
        if record.event not in PARK_KINDS:
            continue
        end = next((r.at for r in records[index + 1 :] if _resumes(r)), None)
        spans.append(
            ParkSpan(
                index + 1,
                record.event,
                record.path,
                record.at,
                end or inputs.run.ended_at or inputs.now,
            )
        )
    return spans


def _resumes(record: GateRecord) -> bool:
    """A signal or a lifecycle record; a `spec_edit` is the operator's too, but the Run stays
    parked through it."""
    signal = record.actor in SIGNALLERS and record.event in SIGNAL_KINDS
    return signal or record.event in LIFECYCLE_EVENTS


def retry_records(inputs: RunInputs) -> dict[str, list[GateRecord]]:
    found: dict[str, list[GateRecord]] = {kind: [] for kind in RETRY_KINDS}
    for record in inputs.records:
        if record.event == RETRY_AUTO:
            found[RETRY_AUTO].append(record)
        elif record.event == REDISPATCH:
            found[REDISPATCH].append(record)
        elif record.event == "retry" and record.actor == "operator":
            found[OPERATOR_RETRY].append(record)
    return found


def _agent_attempts_on(inputs: RunInputs, path: str | None) -> list[AttemptInputs]:
    return sorted(
        (a for a in inputs.attempts if a.row.path == path and a.attempt.role == "agent"),
        key=lambda a: a.attempt.n,
    )


def _started_after(attempts: list[AttemptInputs], at: datetime) -> AttemptInputs | None:
    return next((a for a in attempts if a.attempt.started_at and a.attempt.started_at >= at), None)


def _redispatched(inputs: RunInputs, record: GateRecord) -> list[AttemptInputs]:
    verify = next((r for r in inputs.rows if r.path == record.path), None)
    if verify is None:
        return []
    closing = _started_after(_agent_attempts_on(inputs, verify.path), record.at)
    bound = closing.attempt.started_at if closing else None
    return [
        a
        for a in inputs.attempts
        if a.attempt.role == "agent"
        and a.attempt.n > 1
        and a.row.seq <= verify.seq
        and a.attempt.started_at is not None
        and a.attempt.started_at >= record.at
        and (bound is None or a.attempt.started_at <= bound)
    ]


def created_attempts(inputs: RunInputs) -> dict[str, list[AttemptInputs]]:
    """Per kind, the attempts its records created, each attempt once."""
    records = retry_records(inputs)
    found: dict[str, list[AttemptInputs]] = {kind: [] for kind in RETRY_KINDS}
    for kind in (RETRY_AUTO, OPERATOR_RETRY):
        for record in records[kind]:
            first = _started_after(_agent_attempts_on(inputs, record.path), record.at)
            if first is not None and first not in found[kind]:
                found[kind].append(first)
    for record in records[REDISPATCH]:
        for attempt in _redispatched(inputs, record):
            if attempt not in found[REDISPATCH]:
                found[REDISPATCH].append(attempt)
    return found


def duration(ai: AttemptInputs) -> Decimal | None:
    a = ai.attempt
    if a.started_at is None or a.ended_at is None:
        return None
    return Decimal(int((a.ended_at - a.started_at).total_seconds()))
