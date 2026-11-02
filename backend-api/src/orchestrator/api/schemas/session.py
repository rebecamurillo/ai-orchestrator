"""The HTTP shape of `GET /runs/{id}/session` and `POST /runs/{id}/session/messages`
(AD-23): the Operator's senior session and its turns."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from orchestrator.api.schemas.common import MoneyStr, StorableText, UtcTimestamp
from orchestrator.application.rules.session import SessionScope
from orchestrator.application.use_cases.session_view import SessionTurn, SessionView
from orchestrator.domain.ports.git import Change, ChangeKind
from orchestrator.domain.statuses import StepStatus


class AnchorEditOut(BaseModel):
    """One anchor the session changed, spelled as AD-17 spells a hit."""

    path: str
    kind: ChangeKind

    @classmethod
    def of(cls, change: Change) -> AnchorEditOut:
        return cls(path=change.path, kind=change.kind)


class MessageIn(BaseModel):
    """The Operator's message to the senior; blank text is refused by the use case."""

    text: StorableText


class SessionTurnOut(BaseModel):
    """One turn: the message, the reply file the senior left (`""` when it left none, and
    the attempt's log is then the answer), and how the turn ended."""

    attempt_id: UUID
    turn: int
    status: StepStatus
    message: str
    reply: str
    started_at: UtcTimestamp | None
    ended_at: UtcTimestamp | None
    exit_code: int | None
    cost_usd: MoneyStr | None

    @classmethod
    def of(cls, turn: SessionTurn) -> SessionTurnOut:
        return cls(
            attempt_id=turn.attempt_id,
            turn=turn.turn,
            status=turn.status,
            message=turn.message,
            reply=turn.reply,
            started_at=turn.started_at,
            ended_at=turn.ended_at,
            exit_code=turn.exit_code,
            cost_usd=turn.cost_usd,
        )


class SessionOut(BaseModel):
    """Whether a session holds the Run, whether one can start here, and what it changed."""

    active: bool
    #: True when `session_start` passes AD-13's table at this stop.
    available: bool
    #: The scopes a start at this stop has a frame for.
    scopes: list[SessionScope]
    #: The last `session_start`'s own payload, or `None` before any.
    scope: SessionScope | None
    harness: str | None
    model: str | None
    #: The open session's anchor edits, neither confirmed nor reverted yet.
    anchor_edits: list[AnchorEditOut]
    #: True while one of the last session's turns has not been closed.
    turn_running: bool
    #: The last session's turns, oldest first.
    turns: list[SessionTurnOut]

    @classmethod
    def of(cls, view: SessionView) -> SessionOut:
        return cls(
            active=view.active,
            available=view.available,
            scopes=list(view.scopes),
            scope=view.scope,
            harness=view.harness,
            model=view.model,
            anchor_edits=[AnchorEditOut.of(change) for change in view.anchor_edits],
            turn_running=view.turn_running,
            turns=[SessionTurnOut.of(turn) for turn in view.turns],
        )
