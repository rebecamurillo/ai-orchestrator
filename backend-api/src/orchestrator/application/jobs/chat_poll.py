"""`chat_poll`, the job behind every chat channel (story 3-3, AD-25).

One fire: sweep the stale `posting` rows and the interrupted or stranded notices (4-2), close
every open thread whose stop has ended, whatever its Project's channel (4-2), then, for each
Project with a channel, decrypt its token, open the channel once through
`ChatChannelFactory`, and run the passes in order: post, remind, accept notice, read (4-3),
closing notice and watch (4-2). The watch is skipped for a Project whose read failed this
fire. A channel that cannot be opened still claims its due stops, as `failed`, and skips the
rest.

**Isolation.** The sweep, the channel listing, each Project, and inside each pass each Run,
thread or notice runs in its own `try`. An exception is logged with ids and `error_class`
only, never a token, a message's text or an error's detail, and the job moves on: nothing
raises out of `run_chat_poll`, so nothing reaches another Project or the scheduler. Fires
can overlap, and every pass is safe when two run at once, because every write is claimed
under a lock or by a unique insert first.
"""

from __future__ import annotations

from typing import Final

import structlog

from orchestrator.application.jobs.chat_close import (
    close_threads,
    post_close_notices,
    sweep_notices,
)
from orchestrator.application.jobs.chat_notice import post_notices
from orchestrator.application.jobs.chat_ports import (
    ChatPollPorts,
    OpenedChannel,
    error_class,
    redacted,
)
from orchestrator.application.jobs.chat_post import post_stops, sweep_posting
from orchestrator.application.jobs.chat_read import read_replies
from orchestrator.application.jobs.chat_remind import remind_threads
from orchestrator.application.jobs.chat_watch import watch_threads
from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.ports.chat import ChatError
from orchestrator.domain.ports.crypto import Crypto

log = structlog.get_logger(__name__)

OPEN_FAILED: Final = "channel could not be opened: {name}"

__all__ = ["OPEN_FAILED", "ChatPollPorts", "open_project_channel", "run_chat_poll"]


def run_chat_poll(ports: ChatPollPorts) -> None:
    """One fire of the job. Returns normally whatever happens inside it."""
    try:
        sweep_posting(ports)
    except Exception as error:
        log.warning("chat sweep failed", error_class=error_class(error))
    try:
        sweep_notices(ports)
    except Exception as error:
        log.warning("chat notice sweep failed", error_class=error_class(error))
    try:
        close_threads(ports)
    except Exception as error:
        log.warning("chat close failed", error_class=error_class(error))
    try:
        crypto = ports.crypto()
        with ports.chat.writers.uow:
            channels = ports.chat.channels.list_all()
    except Exception as error:
        log.warning("chat poll failed", error_class=error_class(error))
        return
    for channel in channels:
        try:
            _poll_project(ports, crypto, channel)
        except Exception as error:
            log.warning(
                "chat project failed",
                project_id=str(channel.project_id),
                error_class=error_class(error),
            )


def open_project_channel(
    ports: ChatPollPorts, crypto: Crypto, channel: ProjectChannel
) -> OpenedChannel:
    """The channel opened with its decrypted token, or why it could not be."""
    token = ""
    try:
        token = crypto.decrypt(channel.token_enc)
        chat = ports.factory.open(channel.provider, channel.base_url, channel.channel_id, token)
    except ChatError as error:
        _unopened(channel, error)
        return OpenedChannel(channel, None, token, redacted(error.detail, token))
    except Exception as error:
        _unopened(channel, error)
        return OpenedChannel(channel, None, token, OPEN_FAILED.format(name=error_class(error)))
    return OpenedChannel(channel, chat, token)


def _poll_project(ports: ChatPollPorts, crypto: Crypto, channel: ProjectChannel) -> None:
    opened = open_project_channel(ports, crypto, channel)
    post_stops(ports, opened)
    if opened.chat is None:
        return
    remind_threads(ports, channel, opened.chat)
    post_notices(ports, channel, opened.chat, opened.token)
    read_failed = read_replies(ports, channel, opened.chat, opened.token)
    post_close_notices(ports, channel, opened.chat)
    if not read_failed:
        watch_threads(ports, channel, opened.chat)


def _unopened(channel: ProjectChannel, error: Exception) -> None:
    log.warning(
        "chat channel could not be opened",
        project_id=str(channel.project_id),
        error_class=error_class(error),
    )
