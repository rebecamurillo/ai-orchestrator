"""A stop's chat thread, and the claim on a senior-accept notice (AD-25, story 3-3).

One thread per `(run_id, park_seq)`, for good. `park_kind`, `provider` and `channel_id` are
the values at posting: a thread posted at a `budget` stop keeps that copy when the stop turns
`blocked` at the same `park_seq`, and a thread off the Project's current channel is neither
reminded nor read. `ref` is `None` only while the row is `posting`.

Nothing returns a `closed` or `failed` thread to `open`, and nothing reposts one (hard rule 7).
Every time on a thread comes from the `Clock` port: one backend process, never the
database's `now()`.

A `ChatNotice` is a claim row: the `senior_accept` gate record it names is posted once to the
channel, never as a thread, and a failed post keeps its `error`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, get_args
from uuid import UUID

from orchestrator.domain.ports.chat import ChatProvider
from orchestrator.domain.statuses import ParkKind

ChatThreadState = Literal["posting", "open", "closed", "failed"]
CHAT_THREAD_STATES: Final[tuple[ChatThreadState, ...]] = get_args(ChatThreadState)


@dataclass(frozen=True)
class ChatThread:
    """One stop's thread, as it is stored."""

    id: UUID
    run_id: UUID
    park_seq: int
    park_kind: ParkKind
    provider: ChatProvider
    channel_id: str
    ref: str | None
    cursor: str | None
    state: ChatThreadState
    error: str | None
    last_reminded_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ChatNotice:
    """The claim on posting one `senior_accept` record to the channel."""

    gate_record_id: UUID
    run_id: UUID
    created_at: datetime
    error: str | None = None
