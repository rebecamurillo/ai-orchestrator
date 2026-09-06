"""`/api/v1/harnesses` — reading which harnesses this instance may dispatch to (SPEC CAP-3).

List only: nothing here writes `enabled`, `last_readiness_at` or `failing_check` — that is
Epic 5's readiness use case. The three rows exist once `main.run_migrations` has run.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from orchestrator.api.providers import harness_ports
from orchestrator.api.schemas.common import Page
from orchestrator.api.schemas.harnesses import HarnessOut
from orchestrator.application.use_cases import harnesses as use_cases
from orchestrator.application.use_cases.harnesses import HarnessPorts

router = APIRouter(tags=["harnesses"])

Ports = Annotated[HarnessPorts, Depends(harness_ports)]


@router.get("/harnesses", response_model=Page[HarnessOut], summary="List every harness")
def list_harnesses(ports: Ports) -> Page[HarnessOut]:
    """The three seeded rows, and whatever Epic 5's readiness use case has written onto them."""
    items = [HarnessOut.of(harness) for harness in use_cases.list_harnesses(ports)]
    return Page[HarnessOut](items=items, next_cursor=None)
