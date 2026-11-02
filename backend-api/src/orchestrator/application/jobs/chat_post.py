"""The post pass and the stale `posting` sweep (story 3-3, AD-25).

**A post has three steps**, and the platform call is outside any transaction:

1. *Claim*, one unit of work: lock the Run, re-check the stop is due, read its facts, insert
   the `posting` row (`add` is `ON CONFLICT DO NOTHING`), commit. The Run lock serialises two
   fires; the unique insert is the backstop, so two fires never both post.
2. *Compose and post*, with no unit of work open.
3. *Record*, one unit of work: lock the thread and, if it is still `posting`, make it `open`
   with its `ref`, or `failed` with its error. Anything else means the sweep or another writer
   got there first, and the outcome is dropped.

Nothing is reposted (hard rule 7), and a failed post changes neither the Run nor any status
(AD-8). A stop whose channel could not be opened is still claimed, as `failed`.

**The sweep.** A `posting` row created before this process started, or more than
`POSTING_STALE_MINUTES` ago, is a post whose outcome was lost: it is failed, never reposted,
since the platform may hold a thread nobody reads. A newer row is a post still in flight.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

import structlog

from orchestrator.application.jobs.chat_facts import stop_facts
from orchestrator.application.jobs.chat_ports import (
    ChatPollPorts,
    OpenedChannel,
    error_class,
    redacted,
)
from orchestrator.application.rules.chat_message import StopFacts, compose_stop, run_link
from orchestrator.domain.entities.chat_thread import ChatThread, ChatThreadState
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatChannel, ChatError
from orchestrator.domain.statuses import ParkKind

log = structlog.get_logger(__name__)

POSTING_STALE_MINUTES: Final = 10
INTERRUPTED: Final = "post interrupted; not reposted; a thread may exist and is not read"
INTERNAL: Final = "internal: {name}"
#: The stop the Operator caused; she is at the Run already, so it is not posted.
PAUSED: Final = "paused"


@dataclass(frozen=True)
class _Outcome:
    state: ChatThreadState
    ref: str | None
    error: str | None
    error_class: str | None


def due_kind(run: Run) -> ParkKind | None:
    """The Run's park kind when its stop may be posted, else `None`: parked for a person,
    not paused, and no session holding the Run."""
    if run.status != "needs_you" or run.senior_session or run.terminal_session:
        return None
    return None if run.park_kind == PAUSED else run.park_kind


def post_stops(ports: ChatPollPorts, opened: OpenedChannel) -> None:
    """Post a thread for every due stop of the channel's Project, oldest Run first."""
    chat = ports.chat
    with chat.writers.uow:
        due = [
            run
            for run in reversed(chat.writers.runs.list_by_status("needs_you"))
            if run.project_id == opened.channel.project_id
            and due_kind(run) is not None
            and chat.threads.get_by_stop(run.id, run.park_seq) is None
        ]
    for run in due:
        try:
            _post_one(ports, opened, run.id)
        except Exception as error:
            log.warning(
                "chat post failed",
                run_id=str(run.id),
                park_seq=run.park_seq,
                error_class=error_class(error),
            )


def _post_one(ports: ChatPollPorts, opened: OpenedChannel, run_id: UUID) -> None:
    claimed = _claim(ports, opened, run_id)
    if claimed is None:
        return
    thread, facts = claimed
    if opened.chat is None or facts is None:
        return
    outcome = _send(opened, opened.chat, facts)
    _record(ports, thread, outcome)


def _claim(
    ports: ChatPollPorts, opened: OpenedChannel, run_id: UUID
) -> tuple[ChatThread, StopFacts | None] | None:
    chat = ports.chat
    with chat.writers.uow:
        run = chat.writers.runs.get_for_update(run_id)
        kind = None if run is None else due_kind(run)
        if run is None or kind is None or chat.threads.get_by_stop(run.id, run.park_seq):
            return None
        facts = None
        if opened.chat is not None:
            facts = stop_facts(chat, run, run_link(ports.public_base_url, run.id))
        thread = _new_thread(ports, opened, run, kind)
        if not chat.threads.add(thread):
            return None
        chat.writers.uow.commit()
    if facts is None:
        log.warning(
            "chat thread failed", run_id=str(run_id), park_seq=thread.park_seq, state="failed"
        )
    return thread, facts


def _new_thread(
    ports: ChatPollPorts, opened: OpenedChannel, run: Run, kind: ParkKind
) -> ChatThread:
    now = ports.clock.now()
    unopened = opened.chat is None
    return ChatThread(
        id=new_id(),
        run_id=run.id,
        park_seq=run.park_seq,
        park_kind=kind,
        provider=opened.channel.provider,
        channel_id=opened.channel.channel_id,
        ref=None,
        cursor=None,
        state="failed" if unopened else "posting",
        error=opened.error if unopened else None,
        last_reminded_at=None,
        created_at=now,
        updated_at=now,
    )


def _send(opened: OpenedChannel, chat: ChatChannel, facts: StopFacts) -> _Outcome:
    try:
        text = compose_stop(facts, opened.channel.metadata_only)
        ref = chat.post(text, opened.channel.allowed_users)
    except ChatError as error:
        return _Outcome("failed", None, redacted(error.detail, opened.token), error_class(error))
    except Exception as error:
        name = error_class(error)
        return _Outcome("failed", None, INTERNAL.format(name=name), name)
    return _Outcome("open", ref.id, None, None)


def _record(ports: ChatPollPorts, thread: ChatThread, outcome: _Outcome) -> None:
    chat = ports.chat
    ids = {"run_id": str(thread.run_id), "thread_id": str(thread.id), "park_seq": thread.park_seq}
    with chat.writers.uow:
        current = chat.threads.get_for_update(thread.id)
        if current is None or current.state != "posting":
            log.warning("chat post outcome dropped", **ids, state=outcome.state)
            return
        chat.threads.update(
            replace(
                current,
                state=outcome.state,
                ref=outcome.ref,
                error=outcome.error,
                updated_at=ports.clock.now(),
            )
        )
        chat.writers.uow.commit()
    if outcome.error_class is None:
        log.info("chat thread posted", **ids, state=outcome.state)
    else:
        log.warning(
            "chat thread failed", **ids, state=outcome.state, error_class=outcome.error_class
        )


# ── the sweep ──────────────────────────────────────────────────────────────────────────────


def sweep_posting(ports: ChatPollPorts) -> None:
    """Fail every stale `posting` row, each under its own lock."""
    with ports.chat.writers.uow:
        posting = ports.chat.threads.list_by_state("posting")
    for thread in posting:
        if not _stale(ports, thread, ports.clock.now()):
            continue
        try:
            _fail_stale(ports, thread.id)
        except Exception as error:
            log.warning(
                "chat sweep failed",
                run_id=str(thread.run_id),
                thread_id=str(thread.id),
                error_class=error_class(error),
            )


def _stale(ports: ChatPollPorts, thread: ChatThread, now: datetime) -> bool:
    too_old = now - thread.created_at > timedelta(minutes=POSTING_STALE_MINUTES)
    return thread.created_at < ports.started_at or too_old


def _fail_stale(ports: ChatPollPorts, thread_id: UUID) -> None:
    chat = ports.chat
    now = ports.clock.now()
    with chat.writers.uow:
        current = chat.threads.get_for_update(thread_id)
        if current is None or current.state != "posting" or not _stale(ports, current, now):
            return
        chat.threads.update(replace(current, state="failed", error=INTERRUPTED, updated_at=now))
        chat.writers.uow.commit()
    log.info(
        "chat post interrupted",
        run_id=str(current.run_id),
        thread_id=str(current.id),
        park_seq=current.park_seq,
        state="failed",
    )
