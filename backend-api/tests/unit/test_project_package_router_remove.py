"""`DELETE /projects/{id}/package` refuses over an open initiative (story 1, epic 7; AC6)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from orchestrator.application.use_cases.packages import PackagePorts
from tests.unit.fakes.initiatives import FakeInitiativeRepository
from tests.unit.initiative_fixtures import AT, a_sequence, an_initiative
from tests.unit.test_project_package_router import (
    HTTP_CONFLICT,
    HTTP_NO_CONTENT,
    HTTP_OK,
    PROBLEM,
    Harness,
    put,
)

pytestmark = pytest.mark.asyncio


class WithInitiatives(Harness):
    initiatives = FakeInitiativeRepository()

    def _ports(self) -> PackagePorts:
        return replace(self.world.ports, initiatives=self.initiatives)


def harness(env: dict[str, str], **kw: object) -> WithInitiatives:
    api = WithInitiatives(env)
    api.initiatives = FakeInitiativeRepository(
        [an_initiative(project_id=api.world.project.id, sequence=a_sequence("acme"), **kw)]
    )
    return api


async def test_an_open_initiative_answers_409_and_keeps_the_record(env: dict[str, str]) -> None:
    api = harness(env, slug="snake")
    await put(api)

    async with api.client() as client:
        refused = await client.delete(api.url)
        read = await client.get(api.url)

    assert refused.status_code == HTTP_CONFLICT
    assert refused.headers["content-type"].startswith(PROBLEM)
    assert refused.json()["detail"] == "refused: 1 open initiatives use this package — snake"
    assert read.status_code == HTTP_OK


@pytest.mark.parametrize("kw", [{"cancelled_at": AT}, {"pr_merged_at": AT}])
async def test_only_closed_initiatives_answer_204(
    env: dict[str, str], kw: dict[str, object]
) -> None:
    api = harness(env, **kw)
    await put(api)

    async with api.client() as client:
        removed = await client.delete(api.url)

    assert removed.status_code == HTTP_NO_CONTENT
    assert api.world.packages.get(api.world.project.id) is None
