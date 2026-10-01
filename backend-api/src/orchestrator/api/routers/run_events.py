"""`GET /api/v1/runs/{run_id}/events` — one held connection instead of a poll every 5 s.

The watcher's endpoint (agent-delivery-kit plan §7 v2). Without `wait` it is an ordinary
read. With it, the request is held for up to thirty seconds and answers the moment the Run's
`status` or `updated_at` leaves what the request started from.

**What `since` is for.** A client that answers a park, acts, and calls again would otherwise
be blind to anything that happened between the two calls: the new request would read the
*current* state as its own baseline and then wait on a change it had already missed. Passing
back the `updated_at` of the previous answer makes that change visible on the first read, and
the answer is immediate with `changed: true`. An unparseable or naive `since` is a 422 rather
than a guess, for the reason `api/schemas/common.py` gives for naive timestamps generally.

Its own module beside `run_detail.py`, mounted after `runs.router` for the ordering reason
`api/routers/run.py`'s docstring states. The waiting itself is
`infrastructure/longpoll.py`'s, the read model is `application/use_cases/run_events.py`'s,
and what counts as a change is the one thing this module decides.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers_run_events import RunEventReader, run_event_reader
from orchestrator.api.schemas.run_events import RunEventsOut
from orchestrator.application.use_cases.run_events import RunEvent
from orchestrator.domain.statuses import RunStatus
from orchestrator.infrastructure.longpoll import Watch, hold_until_changed

router = APIRouter(tags=["runs"])

Reader = Annotated[RunEventReader, Depends(run_event_reader)]

#: The longest a client may ask this API to hold a connection. Bounded rather than open-ended
#: so one watcher cannot pin a worker indefinitely, and so the Schemathesis gate stays quick.
MAX_WAIT_S = 30

#: What a change is: the two fields a watcher's baseline is made of.
type ChangeToken = tuple[RunStatus, datetime | None]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


REFUSALS = {
    404: _refusal("No Run has that id."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal(
        "`run_id` is not a UUID, `wait` is outside 0..30, or `since` is not a UTC timestamp."
    ),
}


def change_token(event: RunEvent) -> ChangeToken:
    return event.status, event.updated_at


@router.get(
    "/runs/{run_id}/events",
    response_model=RunEventsOut,
    summary="Read one Run's state, optionally waiting up to 30 s for it to change",
    responses=REFUSALS,
)
async def events(
    run_id: UUID,
    read: Reader,
    wait: Annotated[int, Query(ge=0, le=MAX_WAIT_S)] = 0,
    since: Annotated[AwareDatetime | None, Query()] = None,
) -> RunEventsOut:
    """Answers at once without `wait`; otherwise holds the connection until the Run moves."""

    async def read_once() -> RunEvent:
        # on a worker thread: the read is blocking database I/O, and this coroutine is about
        # to await it up to thirty times without giving up the event loop in between
        return await asyncio.to_thread(read, run_id)

    # before any waiting, so an unknown id is a 404 straight away
    first = await read_once()
    baseline: ChangeToken = (first.status, since if since is not None else first.updated_at)
    watch = Watch(first=first, baseline=baseline, token=change_token)
    event, changed = await hold_until_changed(read_once, watch, wait=wait)
    return RunEventsOut.of(event, changed=changed)
