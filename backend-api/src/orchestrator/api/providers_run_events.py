"""Where `GET /runs/{run_id}/events` gets its read — one *per poll*, not one per request.

Its own module for the reason `providers_run_files.py` is its own: `api/providers.py` is at
the 400-line cap (`test_source_limits.py`), and a capped module gains a sibling rather than
losing a docstring.

Every other read provider here yields ports over one open session for the whole request.
This one cannot: the events route holds its connection open for up to thirty seconds and has
to see writes other transactions make while it waits, and a session that stays open would
answer every poll from the identity map it filled on the first one — a Run that parks mid-
wait would look unchanged until the connection closed. So the dependency yields a callable,
and each call opens, reads and closes a transaction of its own. None of them commits.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from fastapi import Request

from orchestrator.api.providers_base import SESSION_FACTORY, from_state
from orchestrator.application.use_cases.create_run import RunReadPorts
from orchestrator.application.use_cases.run_events import RunEvent, run_event
from orchestrator.infrastructure.db import (
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyUnitOfWork,
)

#: One fresh read of one Run's watcher view. Raises `NotFound` for an id nothing holds.
type RunEventReader = Callable[[UUID], RunEvent]


def run_event_reader(request: Request) -> RunEventReader:
    """A reader the route can call repeatedly, each call its own short read transaction."""
    session_factory = from_state(request, SESSION_FACTORY)

    def read(run_id: UUID) -> RunEvent:
        with SQLAlchemyUnitOfWork(session_factory) as uow:
            return run_event(
                RunReadPorts(
                    runs=SQLAlchemyRunRepository(uow.session),
                    steps=SQLAlchemyStepRunRepository(uow.session),
                ),
                run_id,
            )

    return read
