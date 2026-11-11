"""`/api/v1/instance/*` (SPEC CAP-3, CAP-4, AD-30): the instance's own state, not a Run's.

Its own module, like `routers/queue.py`: no existing router mounts this path and each carries
a frozen route-count assertion.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from orchestrator.api.errors import PROBLEM_MEDIA_TYPE, PROBLEM_SCHEMA_REF, ProblemDetail
from orchestrator.api.providers_instance import activity_ports, hold_ports
from orchestrator.api.schemas.instance import (
    HoldConflictOut,
    HoldIn,
    HoldOut,
    InstanceActivityOut,
    WorkingStepOut,
)
from orchestrator.application.use_cases.instance_activity import (
    ActivityPorts,
    HoldView,
    read_activity,
)
from orchestrator.application.use_cases.instance_hold import (
    HOLD_REFUSED,
    HoldPorts,
    HoldRefused,
    place_hold,
    release_hold,
)

router = APIRouter(tags=["instance"])

Ports = Annotated[ActivityPorts, Depends(activity_ports)]
Holding = Annotated[HoldPorts, Depends(hold_ports)]


@router.get(
    "/instance/activity", response_model=InstanceActivityOut, summary="Read the instance activity"
)
def read_instance_activity(ports: Ports) -> InstanceActivityOut:
    """The working steps and the Runs the engine holds. Writes nothing."""
    return InstanceActivityOut.of(read_activity(ports))


@router.post(
    "/instance/hold",
    status_code=201,
    response_model=HoldOut,
    responses={
        409: {
            "model": HoldConflictOut,
            "description": "Working steps stand; `errors[]` names each one and nothing was held.",
            "content": {
                PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/HoldConflictOut"}}
            },
        },
        422: {
            "model": ProblemDetail,
            "description": "The request broke a rule; `errors[]` names it and the reason.",
            "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
        },
    },
    summary="Hold the instance",
)
def hold_instance(body: HoldIn, ports: Holding) -> HoldOut | JSONResponse:
    """Hold the instance, or answer 409 naming each working step and write nothing."""
    try:
        hold = place_hold(ports, body.ttl_seconds, body.reason)
    except HoldRefused as refused:
        return JSONResponse(
            status_code=409,
            media_type="application/problem+json",
            content=HoldConflictOut(
                type="about:blank",
                title="Conflict",
                status=409,
                detail=HOLD_REFUSED.format(count=len(refused.working)),
                errors=[WorkingStepOut.of(step) for step in refused.working],
            ).model_dump(mode="json"),
        )
    return HoldOut.of(HoldView(hold.held_at, hold.expires_at, hold.reason))


@router.delete(
    "/instance/hold",
    status_code=204,
    response_class=Response,
    summary="Release the instance hold",
)
def release_instance_hold(ports: Holding) -> Response:
    """Delete the hold, whether or not one exists."""
    release_hold(ports.holds, ports.uow)
    return Response(status_code=204)
