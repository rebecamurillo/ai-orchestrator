"""`GET /api/v1/initiatives`, `/projects/{id}/initiatives`, `/initiatives/{id}` (SPEC CAP-4)."""

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
from orchestrator.api.providers_initiatives import initiative_read_ports
from orchestrator.api.schemas.initiatives import InitiativeDetailOut, InitiativeListOut
from orchestrator.application.use_cases import initiative_views
from orchestrator.application.use_cases.initiative_view_types import InitiativeFilter
from orchestrator.application.use_cases.initiative_views import InitiativeReadPorts

router = APIRouter(tags=["initiatives"])

HTTP_NOT_FOUND = 404

Ports = Annotated[InitiativeReadPorts, Depends(initiative_read_ports)]
Filter = Annotated[InitiativeFilter, Query(alias="filter")]


def _refusals(not_found: str) -> dict[int | str, dict[str, object]]:
    def refusal(description: str) -> dict[str, object]:
        return {
            "model": ProblemDetail,
            "description": description,
            "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
        }

    return {
        HTTP_NOT_FOUND: refusal(not_found),
        HTTP_UNPROCESSABLE_CONTENT: refusal("An id or the `filter` is not a valid value."),
    }


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
def read_initiative(initiative_id: UUID, ports: Ports) -> InitiativeDetailOut:
    """The row, its workflows with their steps and turns, and its Runs."""
    return InitiativeDetailOut.of(initiative_views.initiative_detail(ports, initiative_id))
