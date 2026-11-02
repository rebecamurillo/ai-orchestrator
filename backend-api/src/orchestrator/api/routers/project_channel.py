"""`/api/v1/projects/{id}/channel` — read, save and test a Project's chat channel (AD-25).

A router of its own: `test_projects_router.py` pins `routers/projects.py` at four operations.
Each route declares every refusal it can answer, as `routers/projects.py` does, so the
generated client has a type for each. A refused probe is a 200 `{ok: false}`, never a 5xx.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from orchestrator.api.providers_channel import channel_ports
from orchestrator.api.routers.projects import (
    HTTP_CONFLICT,
    HTTP_NOT_FOUND,
    NOT_FOUND_RESPONSE,
    VALIDATION,
    _refusal,
)
from orchestrator.api.schemas.project_channel import ChannelIn, ChannelOut, ChannelTestOut
from orchestrator.application.use_cases import project_channel as use_cases
from orchestrator.application.use_cases.project_channel import ChannelPorts

router = APIRouter(tags=["projects"])

READ_REFUSALS = {**VALIDATION, HTTP_NOT_FOUND: NOT_FOUND_RESPONSE}
WRITE_REFUSALS = {
    **READ_REFUSALS,
    HTTP_CONFLICT: _refusal("The Project is built in and cannot be edited."),
}
TEST_REFUSALS = {**READ_REFUSALS, HTTP_CONFLICT: _refusal("The Project has no channel set.")}

Ports = Annotated[ChannelPorts, Depends(channel_ports)]


@router.get(
    "/projects/{project_id}/channel",
    response_model=ChannelOut,
    summary="Read a Project's chat channel",
    responses=READ_REFUSALS,
)
def get_channel(project_id: UUID, ports: Ports) -> ChannelOut:
    """The stored channel, or `provider: off` when none is set. The token is never returned."""
    return ChannelOut.of(use_cases.get_channel(ports, project_id))


@router.put(
    "/projects/{project_id}/channel",
    response_model=ChannelOut,
    summary="Save or turn off a Project's chat channel",
    responses=WRITE_REFUSALS,
)
def put_channel(project_id: UUID, payload: ChannelIn, ports: Ports) -> ChannelOut:
    """Store the channel with its token encrypted, or delete it for `provider: off`.

    Without `token`, the stored token is kept when the provider is unchanged.
    """
    return ChannelOut.of(use_cases.put_channel(ports, project_id, payload.as_draft()))


@router.post(
    "/projects/{project_id}/channel/test",
    response_model=ChannelTestOut,
    summary="Probe a Project's saved chat channel",
    responses=TEST_REFUSALS,
)
def test_channel(project_id: UUID, ports: Ports) -> ChannelTestOut:
    """One probe of the saved channel, with no retry. A refusal answers `ok: false` with the
    platform's own text."""
    return ChannelTestOut.of(use_cases.test_channel(ports, project_id))
