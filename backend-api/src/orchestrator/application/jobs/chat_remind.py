"""The remind pass (story 3-3, D2, D3): a mentioning reply in a stop's thread every
`CHAT_REMINDER_HOURS` while the Run stays at that stop.

A thread is due when it is `open`, on the channel this fire opened, its Run is `needs_you`
at the thread's `park_seq` with neither session holding it, and the period has passed since
the last reminder or the post. The claim locks the Run, then the thread (4-1's order),
re-checks all of it, sets `last_reminded_at` and commits; the reply is sent after, outside
any transaction. A failed reply is logged, not stored, since 4-3 owns `error` on an open
thread, and `last_reminded_at` stays set: nothing is retried (hard rule 7).

The copy comes from the thread's `park_kind` at posting, so a `budget` thread whose stop
turned `blocked` at the same `park_seq` still links to the Run page.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import structlog

from orchestrator.application.jobs.chat_ports import ChatPollPorts, error_class
from orchestrator.application.rules.chat_message import reminder_text, run_link
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.chat import ChatChannel, ThreadRef

log = structlog.get_logger(__name__)

HOUR = timedelta(hours=1)


def remind_threads(ports: ChatPollPorts, channel: ProjectChannel, chat: ChatChannel) -> None:
    """Remind every due thread of the channel's Project, oldest first."""
    with ports.chat.writers.uow:
        threads = ports.chat.threads.list_open_for_project(channel.project_id)
    now = ports.clock.now()
    for thread in threads:
        if not (_on_channel(thread, channel) and _period_passed(ports, thread, now)):
            continue
        try:
            _remind_one(ports, channel, chat, thread, now)
        except Exception as error:
            log.warning(
                "chat reminder failed",
                run_id=str(thread.run_id),
                thread_id=str(thread.id),
                park_seq=thread.park_seq,
                error_class=error_class(error),
            )


def claim_reminder(ports: ChatPollPorts, thread: ChatThread, now: datetime) -> ChatThread | None:
    """The thread as it was claimed for a reminder now, or `None` when it is not due."""
    chat = ports.chat
    with chat.writers.uow:
        run = chat.writers.runs.get_for_update(thread.run_id)
        current = chat.threads.get_for_update(thread.id)
        if run is None or current is None or not _due(ports, run, current, now):
            return None
        chat.threads.update(replace(current, last_reminded_at=now, updated_at=now))
        chat.writers.uow.commit()
    return current


def _remind_one(
    ports: ChatPollPorts,
    channel: ProjectChannel,
    chat: ChatChannel,
    thread: ChatThread,
    now: datetime,
) -> None:
    claimed = claim_reminder(ports, thread, now)
    if claimed is None or claimed.ref is None:
        return
    hours = (now - claimed.created_at) // HOUR
    text = reminder_text(
        claimed.park_kind,
        claimed.park_seq,
        hours,
        run_link(ports.public_base_url, claimed.run_id),
    )
    chat.reply(ThreadRef(id=claimed.ref), text, mentions=channel.allowed_users)
    log.info(
        "chat reminder sent",
        run_id=str(claimed.run_id),
        thread_id=str(claimed.id),
        park_seq=claimed.park_seq,
    )


def _on_channel(thread: ChatThread, channel: ProjectChannel) -> bool:
    return thread.provider == channel.provider and thread.channel_id == channel.channel_id


def _period_passed(ports: ChatPollPorts, thread: ChatThread, now: datetime) -> bool:
    since = thread.last_reminded_at or thread.created_at
    return now - since >= ports.reminder_hours * HOUR


def _due(ports: ChatPollPorts, run: Run, thread: ChatThread, now: datetime) -> bool:
    return (
        thread.state == "open"
        and thread.ref is not None
        and run.status == "needs_you"
        and run.park_seq == thread.park_seq
        and not run.senior_session
        and not run.terminal_session
        and _period_passed(ports, thread, now)
    )
