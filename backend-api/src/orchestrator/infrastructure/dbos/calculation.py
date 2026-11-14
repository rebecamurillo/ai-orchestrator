"""The metrics calculation's own workflow (AD-6, ARCHITECTURE §9.2a), declared beside the walk
and never inside it.

`run_metrics_calculation(calculation_id)` is two durable steps with the engine's retries off:
`calculation_wait` loops until the calculation may start (no hold, every attempt ended) and
`calculation_run` does the work. Its step sequence is its own: adding it changes nothing the
walker replays, so `DBOS_APPLICATION_VERSION` stays where it is.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from uuid import UUID

import structlog

from orchestrator.application.use_cases.calculate_metrics import (
    CalculationPorts,
    begin_calculation,
    fail_calculation,
    run_calculation,
)
from orchestrator.infrastructure.dbos.facade import DurableEngine
from orchestrator.infrastructure.dbos.walker import HOLD_POLL_SECONDS, WalkerDeps

log = structlog.get_logger(__name__)

NOT_WIRED = "the metrics calculation scope is not wired"
WAIT_FAILED = "metrics calculation could not start"


def build_calculation(engine: DurableEngine, deps: WalkerDeps) -> Callable[[str], None]:
    """Declare the two steps and the workflow on `engine`, and return the workflow."""
    wait = engine.step(_calculation_wait(deps))
    run = engine.step(_calculation_run(deps))

    def run_metrics_calculation(calculation_id: str) -> None:
        wait(calculation_id)
        run(calculation_id)

    return engine.workflow(run_metrics_calculation)


def _scope(deps: WalkerDeps) -> AbstractContextManager[CalculationPorts]:
    if deps.calculation_writes is None:
        raise RuntimeError(NOT_WIRED)
    return deps.calculation_writes()


def _calculation_wait(deps: WalkerDeps) -> Callable[[str], None]:
    def calculation_wait(calculation_id: str) -> None:
        while True:
            with _scope(deps) as ports:
                try:
                    outcome = begin_calculation(ports, UUID(calculation_id))
                except Exception as error:
                    # a raise here ends the workflow with the row still `queued`, and a
                    # re-enqueue of the same id never runs it again: fail it instead
                    log.exception(WAIT_FAILED, calculation_id=calculation_id)
                    fail_calculation(
                        ports, UUID(calculation_id), f"{type(error).__name__}: {error}"
                    )
                    return
            if outcome in ("started", "skip"):
                return
            deps.sleep(HOLD_POLL_SECONDS)

    return calculation_wait


def _calculation_run(deps: WalkerDeps) -> Callable[[str], None]:
    def calculation_run(calculation_id: str) -> None:
        with _scope(deps) as ports:
            run_calculation(ports, UUID(calculation_id))

    return calculation_run
