"""The initiative advance's own workflow (AD-6, AD-37), declared beside the walk and never
inside it.

`run_initiative_advance(advance_id)` is one durable step with the engine's retries off. Its
step sequence is its own, so `DBOS_APPLICATION_VERSION` is not bumped.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from uuid import UUID

from orchestrator.application.use_cases.initiative_advance import AdvancePorts, advance_initiative
from orchestrator.infrastructure.dbos.facade import DurableEngine
from orchestrator.infrastructure.dbos.walker import WalkerDeps

NOT_WIRED = "the initiative advance scope is not wired"


def build_advance(engine: DurableEngine, deps: WalkerDeps) -> Callable[[str], None]:
    """Declare the step and the workflow on `engine`, and return the workflow."""
    run = engine.step(_advance_run(deps))

    def run_initiative_advance(advance_id: str) -> None:
        run(advance_id)

    return engine.workflow(run_initiative_advance)


def _scope(deps: WalkerDeps) -> AbstractContextManager[AdvancePorts]:
    if deps.advance_writes is None:
        raise RuntimeError(NOT_WIRED)
    return deps.advance_writes()


def _advance_run(deps: WalkerDeps) -> Callable[[str], None]:
    def advance_run(workflow_id: str) -> None:
        # the facade starts a workflow with its own id, `{advance_id}:{hex}` (`enqueue_advance`)
        advance_id = workflow_id.partition(":")[0]
        with _scope(deps) as ports:
            advance_initiative(ports, UUID(advance_id))

    return advance_run
