"""`POST /initiatives/{id}/reopen` over ASGI on the shared fakes (epic 9 story 2, AC6)."""

from __future__ import annotations

import pytest

from orchestrator.domain.ids import new_id
from tests.unit.application.initiative_transition_world import TransitionWorld
from tests.unit.test_initiative_actions_router import (
    HTTP_CONFLICT,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_UNPROCESSABLE,
    LIST,
    PROBLEM,
    Harness,
)

ROUND_TWO = 2


class ReopenHarness(Harness):
    def __init__(self, env: dict[str, str]) -> None:
        super().__init__(env)
        self.world = TransitionWorld()  # type: ignore[assignment]


@pytest.fixture
def harness(env: dict[str, str]) -> ReopenHarness:
    return ReopenHarness(env)


def url(harness: ReopenHarness) -> str:
    return f"{LIST}/{harness.world.initiative_row.id}/reopen"  # type: ignore[attr-defined]


async def test_a_valid_reopen_answers_201_with_the_new_run_and_round(
    harness: ReopenHarness,
) -> None:
    async with harness.client() as client:
        response = await client.post(
            url(harness), json={"step": "tech", "reason": "agent exited 1"}
        )

    body = response.json()
    assert response.status_code == HTTP_CREATED
    assert body["round"] == ROUND_TWO
    assert body["run_id"] in {str(r) for r in harness.world.runs.runs}


@pytest.mark.parametrize(
    ("body", "text"),
    [
        ({"step": "deploy", "reason": "why"}, "deploy"),
        ({"step": "gate", "reason": "why"}, "gate"),
        ({"step": "tech", "reason": ""}, "a reopen needs a reason"),
        ({"step": "tech", "reason": "  \n"}, "a reopen needs a reason"),
    ],
)
async def test_a_bad_step_or_reason_is_a_422_problem_and_writes_nothing(
    harness: ReopenHarness, body: dict[str, str], text: str
) -> None:
    async with harness.client() as client:
        response = await client.post(url(harness), json=body)

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM)
    assert text in response.json()["detail"]
    assert harness.world.runs.runs == {}


@pytest.mark.parametrize("closed", ["cancelled_at", "pr_merged_at"])
async def test_a_closed_initiative_is_a_409_and_nothing_is_written(
    harness: ReopenHarness, closed: str
) -> None:
    world = harness.world
    world.initiatives.initiatives[world.initiative_row.id] = world.initiative_row.model_copy(  # type: ignore[attr-defined]
        update={closed: world.harness.clock.now()}  # type: ignore[attr-defined]
    )

    async with harness.client() as client:
        response = await client.post(url(harness), json={"step": "tech", "reason": "why"})

    assert response.status_code == HTTP_CONFLICT
    assert response.headers["content-type"].startswith(PROBLEM)
    assert world.runs.runs == {}
    assert world.remote.calls == []  # type: ignore[attr-defined]


async def test_an_unknown_initiative_is_a_404_problem(harness: ReopenHarness) -> None:
    async with harness.client() as client:
        response = await client.post(
            f"{LIST}/{new_id()}/reopen", json={"step": "tech", "reason": "why"}
        )

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_an_extra_or_missing_field_is_a_422(harness: ReopenHarness) -> None:
    async with harness.client() as client:
        extra = await client.post(url(harness), json={"step": "tech", "reason": "x", "more": 1})
        missing = await client.post(url(harness), json={"step": "tech"})

    assert extra.status_code == missing.status_code == HTTP_UNPROCESSABLE
    assert harness.world.runs.runs == {}


def test_the_reopen_path_publishes_201_and_its_refusals() -> None:
    from fastapi import FastAPI  # noqa: PLC0415

    from orchestrator.api.initiative_routes import install_initiative_routes  # noqa: PLC0415

    app = FastAPI()
    install_initiative_routes(app)
    responses = app.openapi()["paths"]["/api/v1/initiatives/{initiative_id}/reopen"]["post"][
        "responses"
    ]

    assert {"201", "401", "404", "409", "422"} <= set(responses)
