"""`apply_reply_batch` (story 4-1, CAP-12, AD-8, AD-24, AD-25): one thread's new replies,
checked in order, and the first that passes sent as the stop's `answer`.

The batch was read outside any transaction (4-3's read pass), so everything is decided again
in one unit of work that locks the Run, then the thread — the order every writer that locks
both takes. The gate (`rules/chat_reply.py::gate`) is checked once; a moot batch writes
nothing. Each failing reply moves the pending cursor to its own; the first passing reply is
applied through `apply_signal` with actor `chat` and closes the thread at its cursor, in the
same commit, and the engine is told after it, as `signal_run` tells it. Replies after the
winner stay past the cursor.

**A refused apply.** A `DomainError` from `apply_signal` rolls the whole unit of work back.
A second one, under the same locks and gate, moves the cursor past that reply and ends the
batch, so a reply the table refuses is never re-checked.

**The row lock closes the race with the Run page.** `park_seq` does not change on an
answer, so a reply naming that stop would pass AD-24's check; whichever answer commits first
moves the Run to `running`, and every later one fails `stale` under the lock.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from orchestrator.application.rules.chat_reply import (
    ANSWER,
    Outcome,
    answer_payload,
    check,
    gate,
)
from orchestrator.application.rules.signals import row_at
from orchestrator.application.use_cases.signal_apply import (
    Applied,
    SignalPorts,
    apply_signal,
    finish_signal,
)
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import DomainError
from orchestrator.domain.ports.chat import Reply
from orchestrator.domain.ports.repositories import ChatThreadRepository, ProjectChannelRepository
from orchestrator.domain.statuses import Actor
from orchestrator.domain.values import Signal

#: Who a thread reply's answer is recorded as (AD-8 amendment, 2026-11-01).
CHAT: Actor = "chat"

#: Each reply checked, by its id, and what it came to.
Results = list[tuple[str, Outcome]]


@dataclass(frozen=True)
class ReplyPorts:
    """`signal` carries both mode callables, so an answer resumes the agent's session when
    the latest attempt can; the other two are on the same session as its writers."""

    signal: SignalPorts
    threads: ChatThreadRepository
    channels: ProjectChannelRepository


@dataclass(frozen=True)
class _Locked:
    run: Run
    thread: ChatThread
    channel: ProjectChannel


@dataclass(frozen=True)
class _Answered:
    signal: Signal
    applied: Applied


class _Refused(Exception):
    """`apply_signal` refused `reply`, after `results` were decided."""

    def __init__(self, results: Results, reply: Reply) -> None:
        super().__init__(reply.id)
        self.results = results
        self.reply = reply


def apply_reply_batch(ports: ReplyPorts, read: ChatThread, replies: Sequence[Reply]) -> Results:
    """Check `replies`, read after `read.cursor`, against the thread and its Run as they are
    now. Logs nothing: the outcomes are for the caller."""
    if not replies:
        return []
    try:
        results, answered = _check_batch(ports, read, replies)
    except _Refused as refused:
        return _move_past(ports, read, replies, refused)
    if answered is not None:
        finish_signal(ports.signal, read.run_id, answered.signal, answered.applied)
    return results


def close_thread(ports: ReplyPorts, thread: ChatThread, cursor: str) -> None:
    """The one write that closes a thread: `closed`, at `cursor`."""
    now = ports.signal.writers.clock.now()
    ports.threads.update(replace(thread, state="closed", cursor=cursor, updated_at=now))


def _check_batch(
    ports: ReplyPorts, read: ChatThread, replies: Sequence[Reply]
) -> tuple[Results, _Answered | None]:
    writers = ports.signal.writers
    with writers.uow:
        locked = _lock(ports, read)
        if not isinstance(locked, _Locked):
            return _all(replies, locked), None
        rows = writers.steps.list_for_run(locked.run.id)
        park_row = row_at(rows, locked.run.park_path)
        results: Results = []
        for reply in replies:
            outcome = check(locked.channel, locked.thread, reply, locked.run, park_row, rows)
            if outcome is None:
                answered = _answer(ports, locked, reply, results)
                writers.uow.commit()
                return [*results, (reply.id, "answered")], answered
            results.append((reply.id, outcome))
        _advance(ports, locked.thread, replies[-1].cursor)
        writers.uow.commit()
    return results, None


def _answer(ports: ReplyPorts, locked: _Locked, reply: Reply, results: Results) -> _Answered:
    thread = locked.thread
    signal = Signal(
        kind=ANSWER,
        payload=answer_payload(locked.channel, thread, reply),
        stop=thread.park_seq,
    )
    try:
        applied = apply_signal(ports.signal, locked.run, signal, actor=CHAT)
    except DomainError as error:
        raise _Refused(list(results), reply) from error
    close_thread(ports, thread, reply.cursor)
    return _Answered(signal=signal, applied=applied)


def _move_past(
    ports: ReplyPorts, read: ChatThread, replies: Sequence[Reply], refused: _Refused
) -> Results:
    writers = ports.signal.writers
    with writers.uow:
        locked = _lock(ports, read)
        if not isinstance(locked, _Locked):
            return _all(replies, locked)
        _advance(ports, locked.thread, refused.reply.cursor)
        writers.uow.commit()
    return [*refused.results, (refused.reply.id, "refused")]


def _lock(ports: ReplyPorts, read: ChatThread) -> _Locked | Outcome:
    """The Run, then the thread, under their row locks, and the Project's channel now; or
    why the batch is moot."""
    run = ports.signal.writers.runs.get_for_update(read.run_id)
    thread = ports.threads.get_for_update(read.id)
    channel = ports.channels.get(run.project_id) if run is not None else None
    moot = gate(thread, read.cursor, channel)
    if moot is not None or run is None or thread is None or channel is None:
        return moot or "superseded"
    return _Locked(run=run, thread=thread, channel=channel)


def _advance(ports: ReplyPorts, thread: ChatThread, cursor: str) -> None:
    now = ports.signal.writers.clock.now()
    ports.threads.update(replace(thread, cursor=cursor, updated_at=now))


def _all(replies: Sequence[Reply], outcome: Outcome) -> Results:
    return [(reply.id, outcome) for reply in replies]
