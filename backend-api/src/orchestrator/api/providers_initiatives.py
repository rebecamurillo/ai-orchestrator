"""Ports for the four initiative routes (AD-12, AD-13, S6, S8).

A module of its own for the reason `providers_run_files.py` and `providers_trajectories.py`
are: `api/providers.py` sits at its 400-line cap (`test_source_limits.py`), and the
split-not-trim rule says a capped module gains a sibling rather than a trimmed docstring.

`_preflight_ports` is reused from `api/providers.py` rather than restated here — pre-flight's
wiring is one thing, and an initiative pre-flights every one of its would-be epic Runs
through exactly it.

`initiative_signal_ports` (S8) wires `POST /initiatives/{slug}/signals` on plain `SignalPorts`
— the same type every fan-out `signal_run(ports, run_id, signal)` call reuses (AD-13's own
sentence: "no second writer"). It opens one `WriterPorts` session the way `dispatch_ports`
opens its own second one, rather than reaching for `signal_effect_ports`
(`api/providers.py`): that dependency's `cancel` cleanup (`Git`/`ProcessRunner`) belongs to a
single Run's own signal surface, and `signal_initiative` calls `signal_run` directly, not
`handle_signal`, precisely so a slug fan-out is nothing more than AD-13's table applied member
by member.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request

from orchestrator.api.providers import _preflight_ports
from orchestrator.api.providers_base import ENGINE, SESSION_FACTORY, SETTINGS, from_state
from orchestrator.application.use_cases.create_run import CreateRunPorts
from orchestrator.application.use_cases.dispatch_initiative import DispatchPorts
from orchestrator.application.use_cases.initiative_view import InitiativeReadPorts
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.signal_run import SignalPorts
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyRepositoryRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyUnitOfWork,
    open_writer_ports,
)
from orchestrator.infrastructure.tracing import build_tracer


def initiative_preflight_ports(request: Request) -> Iterator[PreflightPorts]:
    """The ports `POST /initiatives/preflight` runs on. Writes nothing, still one
    transaction — the way `preflight_ports` does for its own read-only route."""
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield _preflight_ports(request, uow, "initiative pre-flight")


def dispatch_ports(request: Request) -> Iterator[DispatchPorts]:
    """The ports `POST /initiatives` runs on: `create_run`'s own, plus the writer ports the
    wave-0 enqueue commits its `engine_ref` through.

    Two sessions, for the same reason `signal_effect_ports` opens two: the writer ports own
    the short units of work `enqueue_saved_run` opens and closes per Run, and the creation
    path owns the one the plans are written in.
    """
    session_factory = from_state(request, SESSION_FACTORY)
    engine: WorkflowEngine = from_state(request, ENGINE)
    settings = from_state(request, SETTINGS)
    with (
        SQLAlchemyUnitOfWork(session_factory) as uow,
        open_writer_ports(session_factory, engine=engine) as writers,
    ):
        yield DispatchPorts(
            create=CreateRunPorts(
                preflight=_preflight_ports(request, uow, "dispatch_initiative"),
                engine=engine,
                steps=SQLAlchemyStepRunRepository(uow.session),
                uow=uow,
                clock=SystemClock(),
                tracer=build_tracer(settings),
            ),
            writers=writers,
        )


def initiative_read_ports(request: Request) -> Iterator[InitiativeReadPorts]:
    """The ports `GET /initiatives/{slug}` reads through. Writes nothing."""
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield InitiativeReadPorts(
            runs=SQLAlchemyRunRepository(uow.session),
            repositories=SQLAlchemyRepositoryRepository(uow.session),
        )


def initiative_signal_ports(request: Request) -> Iterator[SignalPorts]:
    """The ports `POST /initiatives/{slug}/signals` runs on (S8): one `WriterPorts` session
    and the engine, exactly what `signal_run` itself needs — see the module docstring for
    why this is not `signal_effect_ports`."""
    session_factory = from_state(request, SESSION_FACTORY)
    engine: WorkflowEngine = from_state(request, ENGINE)
    with open_writer_ports(session_factory, engine=engine) as writers:
        yield SignalPorts(writers=writers, engine=engine)
