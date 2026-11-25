"""`PUT /api/v1/projects/{id}/run-defaults` over ASGI with the fakes (story 1 of epic 6)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
import pytest

from orchestrator.api.providers_initiatives import advance_retry_ports
from orchestrator.application.use_cases.advance_retry import AdvanceRetryPorts
from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.domain.entities.project import READINESS_PROJECT_SLUG, Project
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.initiatives import FakeInitiativeAdvanceRepository, FakeInitiativeRepository
from tests.unit.initiative_fixtures import a_sequence
from tests.unit.test_projects_router import (
    HTTP_CONFLICT,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNPROCESSABLE,
    PROJECTS,
    UNKNOWN_ID,
    Harness,
    a_payload,
    create,
)


class RetryHarness(Harness):
    """`Harness` with the advance-retry dependency (epic 8 story 3, 2026-11-25) over fakes."""

    def __init__(self, env: dict[str, str]) -> None:
        super().__init__(env)
        self.initiatives = FakeInitiativeRepository()
        self.advances = FakeInitiativeAdvanceRepository()
        self.retry_uow = FakeUnitOfWork()
        self.engine = FakeWorkflowEngine(clock=FakeClock(), uow=self.retry_uow)
        self.app.dependency_overrides[advance_retry_ports] = self._retry

    def _retry(self) -> AdvanceRetryPorts:
        return AdvanceRetryPorts(
            initiatives=self.initiatives,
            advances=self.advances,
            uow=self.retry_uow,
            engine=self.engine,
        )


@pytest.fixture
def api(env: dict[str, str]) -> RetryHarness:
    return RetryHarness(env)


KEYS = (
    "default_budget_usd",
    "default_harness",
    "default_model",
    "default_autonomy",
    "default_senior_model",
)
FULL: dict[str, Any] = {
    "default_budget_usd": "25.00",
    "default_harness": "claude",
    "default_model": "claude-opus-5-5",
    "default_autonomy": "auto",
    "default_senior_model": "claude-opus-5-5",
}


def money_equal(body: dict[str, Any]) -> dict[str, Any]:
    """The money string renders six decimals (`MoneyStr`); compare it as the Decimal it is."""
    assert Decimal(body["default_budget_usd"]) == Decimal("25.00")
    return {**body, "default_budget_usd": "25.00"}


NULLS: dict[str, Any] = dict.fromkeys(KEYS)


async def put(api: Harness, project_id: str, body: dict[str, Any]) -> httpx.Response:
    async with api.client() as client:
        return await client.put(f"{PROJECTS}/{project_id}/run-defaults", json=body)


async def get(api: Harness, project_id: str) -> dict[str, Any]:
    async with api.client() as client:
        return (await client.get(f"{PROJECTS}/{project_id}")).json()  # type: ignore[no-any-return]


async def test_a_new_project_reads_every_default_as_null(api: Harness) -> None:
    created = (await create(api)).json()

    read = await get(api, created["id"])
    async with api.client() as client:
        listed = (await client.get(PROJECTS)).json()["items"][0]

    for body in (created, read, listed):
        assert {key: body[key] for key in KEYS} == NULLS


async def test_the_defaults_are_set_and_read_back(api: Harness) -> None:
    identifier = (await create(api)).json()["id"]

    response = await put(api, identifier, FULL)

    assert response.status_code == HTTP_OK
    assert money_equal({key: response.json()[key] for key in KEYS}) == FULL
    assert money_equal({key: (await get(api, identifier))[key] for key in KEYS}) == FULL


async def test_all_null_clears_them(api: Harness) -> None:
    identifier = (await create(api)).json()["id"]
    await put(api, identifier, FULL)

    response = await put(api, identifier, NULLS)

    assert response.status_code == HTTP_OK
    assert {key: (await get(api, identifier))[key] for key in KEYS} == NULLS


async def test_a_zero_or_negative_budget_is_a_422_naming_the_field_and_stores_nothing(
    api: Harness,
) -> None:
    identifier = (await create(api)).json()["id"]

    for budget in ("0", "-5"):
        response = await put(api, identifier, {**FULL, "default_budget_usd": budget})
        assert response.status_code == HTTP_UNPROCESSABLE
        assert "default_budget_usd" in str(response.json()["errors"])

    assert {key: (await get(api, identifier))[key] for key in KEYS} == NULLS


async def test_a_sub_cent_budget_reads_back_as_sent_not_as_zero(api: Harness) -> None:
    """Operator ruling, 2026-11-24: `0.004` is a valid budget and is kept, not rounded to 0."""
    identifier = (await create(api)).json()["id"]

    response = await put(api, identifier, {**FULL, "default_budget_usd": "0.004"})

    assert response.status_code == HTTP_OK
    assert Decimal(response.json()["default_budget_usd"]) == Decimal("0.004")
    assert Decimal((await get(api, identifier))["default_budget_usd"]) == Decimal("0.004")


async def test_a_malformed_body_is_a_422(api: Harness) -> None:
    identifier = (await create(api)).json()["id"]
    missing = {k: v for k, v in FULL.items() if k != "default_model"}

    for body in (
        {**FULL, "extra": 1},
        missing,
        {**FULL, "default_harness": "Bad Harness"},
        {**FULL, "default_model": ""},
        {**FULL, "default_senior_model": ""},
        {**FULL, "default_autonomy": "manual"},
    ):
        assert (await put(api, identifier, body)).status_code == HTTP_UNPROCESSABLE


async def test_the_full_replace_put_keeps_the_stored_defaults(api: Harness) -> None:
    identifier = (await create(api)).json()["id"]
    await put(api, identifier, FULL)

    async with api.client() as client:
        response = await client.put(f"{PROJECTS}/{identifier}", json=a_payload(name="Renamed"))

    assert response.status_code == HTTP_OK
    assert money_equal({key: response.json()[key] for key in KEYS}) == FULL


async def test_an_unknown_project_is_a_404(api: Harness) -> None:
    assert (await put(api, UNKNOWN_ID, FULL)).status_code == HTTP_NOT_FOUND


async def test_the_readiness_project_is_a_409(api: Harness) -> None:
    now = datetime(2026, 3, 4, tzinfo=UTC)
    readiness = Project(
        id=new_id(),
        slug=READINESS_PROJECT_SLUG,
        name=READINESS_PROJECT_SLUG,
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        builtin=True,
        created_at=now,
        updated_at=now,
    )
    api.projects.add(readiness)

    response = await put(api, str(readiness.id), FULL)

    assert response.status_code == HTTP_CONFLICT


async def test_setting_the_defaults_wakes_an_advance_blocked_for_want_of_a_budget(
    api: RetryHarness,
) -> None:
    """Epic 8 story 3, AC8: the PUT enqueues the advance `no project budget` blocked."""
    identifier = (await create(api)).json()["id"]
    now = api.clock.now()
    initiative = Initiative(
        id=new_id(),
        project_id=UUID(identifier),
        repository_id=new_id(),
        slug="snake",
        name="Snake",
        first_message="hi",
        sequence=a_sequence(),
        created_at=now,
    )
    api.initiatives.add(initiative)
    blocked = InitiativeAdvance(
        id=new_id(),
        initiative_id=initiative.id,
        from_run_id=new_id(),
        round=1,
        position=0,
        blocked_reason="no project budget",
    )
    other = blocked.model_copy(update={"id": new_id(), "position": 1, "blocked_reason": "x"})
    api.advances.add(blocked)
    api.advances.add(other)

    response = await put(api, identifier, FULL)

    assert response.status_code == HTTP_OK
    assert api.engine.calls == [("enqueue_advance", blocked.id)]
