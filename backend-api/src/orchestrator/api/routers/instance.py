"""`/api/v1/instance/*` (SPEC CAP-3, AD-30): the instance's own state, not a Run's.

Its own module, like `routers/queue.py`: no existing router mounts this path and each carries
a frozen route-count assertion. Story 4 adds the hold routes here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from orchestrator.api.providers_instance import activity_ports
from orchestrator.api.schemas.instance import InstanceActivityOut
from orchestrator.application.use_cases.instance_activity import ActivityPorts, read_activity

router = APIRouter(tags=["instance"])

Ports = Annotated[ActivityPorts, Depends(activity_ports)]


@router.get(
    "/instance/activity", response_model=InstanceActivityOut, summary="Read the instance activity"
)
def read_instance_activity(ports: Ports) -> InstanceActivityOut:
    """The working steps and the Runs the engine holds. Writes nothing."""
    return InstanceActivityOut.of(read_activity(ports))
