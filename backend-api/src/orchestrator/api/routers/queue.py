"""`/api/v1/queue` (SPEC CAP-11, FR-13, FR-25): the queue as the engine sees it.

Its own module — none of `runs.py`, `run.py`, `signals.py` or `repository_init.py` mounts
this path, and each of those already carries its own frozen route-count assertion
(`tests/unit/test_runs_router.py`, `test_run_router.py`, `test_signals_router.py`,
`test_repository_init_router.py`) — so a new route belongs in a new module on the same
`/api/v1` prefix, mounted through `main.py`'s `_mount` helper like every router but the two
`test_graph_text_router.py` reads by AST.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from orchestrator.api.providers import queue_ports
from orchestrator.api.schemas.queue import QueueOut
from orchestrator.application.use_cases.queue import QueuePorts, list_queue

router = APIRouter(tags=["queue"])

Ports = Annotated[QueuePorts, Depends(queue_ports)]


@router.get("/queue", response_model=QueueOut, summary="Read the queue")
def read_queue(ports: Ports) -> QueueOut:
    """Every Run the engine is holding, joined with the reason it waits. Writes nothing."""
    return QueueOut.of(list_queue(ports))
