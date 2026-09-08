"""Wires `StepPorts.spend_writes` onto an `agent_tail_fixtures.a_tail_world()` world (5.7).

`agent_fixtures.py`'s own `_writes()` refuses `WriterPorts.runs`/`.steps` on purpose (AD-8:
the agent kind writes only through `.attempts`), so the budget read needs a *second* scope
of its own — `SpendPorts`, opened the way `infrastructure/db/writers.py::open_spend_ports`
opens it for real, over the shared fakes instead of a session. Built here, additively, on
top of the frozen `a_tail_world`/`World` rather than by editing either.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal

from orchestrator.application.use_cases.spend import SpendPorts
from orchestrator.domain.ports.gateway import AttemptSpend, ModelSpend
from tests.unit.application.steps.agent_fixtures import World
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository


def with_spend(world: World, *, gateway: FakeGateway | None = None) -> World:
    """The same `World`, with a real `spend_writes` scope over its own Run/row/attempt.

    A fresh `FakeUnitOfWork` per call, the same reason `agent_fixtures._writes` gives one
    per `attempt_writes()` call: `record_attempt_spend` opens and commits its own.
    """
    runs = FakeRunRepository([world.run])
    steps = FakeStepRunRepository([world.row])
    attempts = FakeAttemptRepository([world.attempt])
    the_gateway = gateway if gateway is not None else FakeGateway()

    @contextmanager
    def open_scope() -> Iterator[SpendPorts]:
        yield SpendPorts(
            gateway=the_gateway, runs=runs, steps=steps, attempts=attempts, uow=FakeUnitOfWork()
        )

    ports = replace(world.ctx.ports, spend_writes=open_scope)
    return replace(world, ctx=replace(world.ctx, ports=ports))


def spend(usd: str, tokens_in: int = 1, tokens_out: int = 1) -> AttemptSpend:
    """A settled `AttemptSpend` of exactly `usd` — the shape a scripted `FakeGateway` answer
    needs to price an attempt without going through the provisional fallback."""
    amount = Decimal(usd)
    return AttemptSpend(
        usd=amount,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        by_model=(ModelSpend(model="m", usd=amount, tokens_in=tokens_in, tokens_out=tokens_out),),
        calls=1,
        provisional=False,
    )
