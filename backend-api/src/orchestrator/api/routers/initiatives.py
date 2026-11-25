"""The initiative reads (SPEC CAP-4) and its three actions: create, cancel, start-next (CAP-5)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers_initiatives import (
    initiative_ports,
    initiative_read_ports,
    open_initiative_ports,
)
from orchestrator.api.schemas.initiatives import (
    InitiativeDetailOut,
    InitiativeIn,
    InitiativeListOut,
    StartNextIn,
)
from orchestrator.application.use_cases import initiative_start_next, initiative_views, initiatives
from orchestrator.application.use_cases.initiative_view_types import InitiativeFilter
from orchestrator.application.use_cases.initiative_views import InitiativeReadPorts
from orchestrator.application.use_cases.initiatives import InitiativePorts
from orchestrator.application.use_cases.open_initiative import OpenInitiativePorts, open_initiative

router = APIRouter(tags=["initiatives"])

HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_CREATED = 201

Ports = Annotated[InitiativeReadPorts, Depends(initiative_read_ports)]
WritePorts = Annotated[InitiativePorts, Depends(initiative_ports)]
OpenPorts = Annotated[OpenInitiativePorts | None, Depends(open_initiative_ports)]
Filter = Annotated[InitiativeFilter, Query(alias="filter")]


def _refusals(not_found: str, *, conflict: str | None = None) -> dict[int | str, dict[str, object]]:
    def refusal(description: str) -> dict[str, object]:
        return {
            "model": ProblemDetail,
            "description": description,
            "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
        }

    answers = {
        HTTP_NOT_FOUND: refusal(not_found),
        HTTP_UNPROCESSABLE_CONTENT: refusal("An id, the `filter` or the body is not valid."),
    }
    if conflict is not None:
        answers[HTTP_CONFLICT] = refusal(conflict)
    return answers


@router.get(
    "/initiatives",
    response_model=InitiativeListOut,
    summary="List initiatives",
    responses=_refusals("No Project has that id."),
)
def list_initiatives(
    ports: Ports, project_id: UUID | None = None, filter_: Filter = "ongoing"
) -> InitiativeListOut:
    """Every initiative with its computed status, newest change first."""
    return InitiativeListOut.of(
        initiative_views.list_initiatives(ports, project_id=project_id, filter=filter_)
    )


@router.get(
    "/projects/{project_id}/initiatives",
    response_model=InitiativeListOut,
    summary="List a Project's initiatives",
    responses=_refusals("No Project has that id."),
)
def list_project_initiatives(
    project_id: UUID, ports: Ports, filter_: Filter = "ongoing"
) -> InitiativeListOut:
    """`GET /initiatives?project_id=` for one Project."""
    return InitiativeListOut.of(
        initiative_views.list_initiatives(ports, project_id=project_id, filter=filter_)
    )


@router.get(
    "/initiatives/{initiative_id}",
    response_model=InitiativeDetailOut,
    summary="Read an initiative",
    responses=_refusals("No initiative has that id."),
)
def read_initiative(
    initiative_id: UUID, ports: Ports, open_ports: OpenPorts
) -> InitiativeDetailOut:
    """The row, its workflows with their steps and turns, and its Runs.

    `?opened=true` moves `last_opened_at` to now first and marks the files changed since the
    previous view; without it nothing is written.
    """
    if open_ports is None:
        return InitiativeDetailOut.of(initiative_views.initiative_detail(ports, initiative_id))
    prior = open_initiative(open_ports, initiative_id)
    return InitiativeDetailOut.of(
        initiative_views.initiative_detail(ports, initiative_id, prior=prior)
    )


@router.post(
    "/initiatives",
    status_code=HTTP_CREATED,
    response_model=InitiativeDetailOut,
    summary="Create an initiative",
    responses=_refusals(
        "No Project has that id.",
        conflict="The slug is held by an open initiative, or the hub refuses the branch.",
    ),
)
def create_initiative_route(
    body: InitiativeIn, ports: WritePorts, reads: Ports
) -> InitiativeDetailOut:
    """Branch `spec/{slug}` on the hub and start the spec Run."""
    created = initiatives.create_initiative(
        ports, body.project_id, name=body.name, first_message=body.first_message
    )
    return InitiativeDetailOut.of(initiative_views.initiative_detail(reads, created.id))


@router.post(
    "/initiatives/{initiative_id}/cancel",
    response_model=InitiativeDetailOut,
    summary="Cancel an initiative",
    responses=_refusals(
        "No initiative has that id.", conflict="The initiative is done or cancelled."
    ),
)
def cancel_initiative_route(
    initiative_id: UUID, ports: WritePorts, reads: Ports
) -> InitiativeDetailOut:
    """Cancel every live Run and delete `spec/{slug}`."""
    cancelled = initiatives.cancel_initiative(ports, initiative_id)
    return InitiativeDetailOut.of(initiative_views.initiative_detail(reads, cancelled.id))


@router.post(
    "/initiatives/{initiative_id}/start-next",
    response_model=InitiativeDetailOut,
    summary="Force the next conversation step",
    responses=_refusals(
        "No initiative has that id.",
        conflict="No conversation step is open, the next is not forceable, or the stop is stale.",
    ),
)
def start_next_route(
    initiative_id: UUID, body: StartNextIn, ports: WritePorts, reads: Ports
) -> InitiativeDetailOut:
    """One forced `skip_step` naming the stop the operator saw."""
    moved = initiative_start_next.start_next(ports, initiative_id, body.park_seq)
    return InitiativeDetailOut.of(initiative_views.initiative_detail(reads, moved.id))
