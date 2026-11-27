"""The two enqueues a status writer makes after its commit: a saved Run, and a done Run's
dependents (AD-8, AD-12). Moved out of `writers.py`, which re-exports both.

`writers` imports this module at the top, so this one imports it only inside the functions
that need it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.engine import WorkflowEngine

if TYPE_CHECKING:
    from orchestrator.application.use_cases.writers import WriterPorts


def enqueue_saved_run(ports: WriterPorts, engine: WorkflowEngine | None, run: Run) -> None:
    """Two-phase: enqueue first, then commit the returned `engine_ref` in its own UoW.

    The order is AD-8's: the engine only ever sees a Run whose row is already durable. A
    `None` engine degrades to a no-op — every call site that predates story 5-4, and
    `park_dependents`, which can never reach this branch anyway.

    The partition key is AD-12's: the Run's **declared** branch, or `base_branch` for a plan
    that declares none. Two callers share it rather than spelling it twice —
    `resolve_dependent` below, and any other caller that saves a Run in exactly this
    state: saved, `engine_ref` empty, nothing waited on.
    """
    from orchestrator.application.use_cases import writers  # noqa: PLC0415

    if engine is None:
        return
    partition_key = (
        f"{run.repository_id}:{run.partition_branch or run.inputs.get('base_branch', '')}"
    )
    engine_ref = engine.enqueue(run.id, partition_key=partition_key, lane=run.lane)
    with ports.uow:
        refreshed = ports.runs.get(run.id)
        if refreshed is not None:
            writers.set_run(ports, refreshed, engine_ref=engine_ref)
        ports.uow.commit()


def enqueue_dependents(ports: WriterPorts, engine: WorkflowEngine | None, run: Run) -> None:
    """Resolve every dependent of `run` after `run`'s `done` write is committed.

    Called with no transaction open, so each resolution owns its own. Idempotent: a
    dependent that was already enqueued carries an `engine_ref` and is invisible to
    `list_dependents`. Degrades to a no-op when `engine` is None (every call site that
    predates story 5-4).
    """
    from orchestrator.application.use_cases import writers  # noqa: PLC0415

    if engine is None:
        return
    for dep in ports.runs.list_dependents(run.id):
        writers.resolve_dependent(ports, engine, dep)
