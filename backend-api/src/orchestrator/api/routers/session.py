"""`GET /api/v1/runs/{run_id}/session`, `POST .../session/messages` and `POST .../session/retry`
(AD-23): the Operator's senior session on one Run, one message to it, and the restart of its
last failed turn.

The session opens and closes through `POST /runs/{id}/signals` (`session_start`,
`session_end`). A message queues one turn and answers 202 before the senior has run; the
turn's progress is read back here.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers_session import message_ports, session_ports
from orchestrator.api.schemas.session import MessageIn, SessionOut, SessionTurnOut
from orchestrator.application.use_cases.session_checks import SessionPorts
from orchestrator.application.use_cases.session_retry import retry_turn
from orchestrator.application.use_cases.session_turn import MessagePorts, post_message
from orchestrator.application.use_cases.session_view import session_view

router = APIRouter(tags=["runs"])

Ports = Annotated[SessionPorts, Depends(session_ports)]
Messages = Annotated[MessagePorts, Depends(message_ports)]

HTTP_ACCEPTED = 202
HTTP_CREATED = 201
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_SERVER_ERROR = 500


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


REFUSALS: dict[int | str, dict[str, object]] = {
    HTTP_NOT_FOUND: _refusal("No Run has that id."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("`run_id` does not parse as a UUID."),
}

MESSAGE_REFUSALS: dict[int | str, dict[str, object]] = {
    HTTP_NOT_FOUND: _refusal("No Run has that id."),
    HTTP_CONFLICT: _refusal("No senior session is open, a turn is running, or no budget remains."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("The text is empty, or the body does not parse."),
    HTTP_SERVER_ERROR: _refusal("The turn could not be enqueued; it was closed `error`."),
}

RETRY_REFUSALS: dict[int | str, dict[str, object]] = {
    HTTP_NOT_FOUND: _refusal("No Run has that id."),
    HTTP_CONFLICT: _refusal(
        "No session is open, a turn is running, the last turn did not fail, or no budget remains."
    ),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("`run_id` does not parse as a UUID."),
    HTTP_SERVER_ERROR: _refusal("The turn could not be enqueued; it was closed `error`."),
}


@router.get(
    "/runs/{run_id}/session",
    response_model=SessionOut,
    summary="Read the Operator's senior session on a Run",
    responses=REFUSALS,
)
def get_session(run_id: UUID, ports: Ports) -> SessionOut:
    return SessionOut.of(session_view(ports, run_id))


@router.post(
    "/runs/{run_id}/session/messages",
    status_code=HTTP_ACCEPTED,
    response_model=SessionTurnOut,
    summary="Send the senior session one message, queued as its next turn",
    responses=MESSAGE_REFUSALS,
)
def post_session_message(run_id: UUID, payload: MessageIn, ports: Messages) -> SessionTurnOut:
    return SessionTurnOut.of(post_message(ports, run_id, payload.text))


@router.post(
    "/runs/{run_id}/session/retry",
    status_code=HTTP_CREATED,
    response_model=SessionTurnOut,
    summary="Restart the last failed turn",
    responses=RETRY_REFUSALS,
)
def post_session_retry(run_id: UUID, ports: Messages) -> SessionTurnOut:
    return SessionTurnOut.of(retry_turn(ports, run_id))
