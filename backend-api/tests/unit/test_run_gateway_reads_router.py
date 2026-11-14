"""GET /runs/{id}/metrics/gateway-reads over fakes (epic 2 story 6: AC1, AC2, AC4)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.api.routers import run_gateway_reads
from orchestrator.domain.entities.facts import GatewayRead, UsageFact
from orchestrator.domain.ids import new_id
from tests.unit.application.metrics_fixed_run import RUN_ID, S0, T0
from tests.unit.test_run_metrics_router import HTTP_NOT_FOUND, HTTP_UNAUTHORIZED, PROBLEM, Api

ATTEMPT_COUNT = 12
HTTP_OK = 200


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


URL = f"/api/v1/runs/{RUN_ID}/metrics/gateway-reads"


async def test_the_reads_of_an_attempt_come_in_time_order_with_the_harness_figure(
    api: Api,
) -> None:
    attempt_id = api.read.attempts.attempts[UUID(int=2001)].id  # type: ignore[attr-defined]
    api.read.gateway_reads.add(
        GatewayRead(
            id=new_id(),
            attempt_id=attempt_id,
            run_id=RUN_ID,
            read_at=T0 + timedelta(days=1),
            trigger="run_end",
            provisional=False,
            usd=Decimal("0.58"),
        ),
        (UsageFact(source="harness", model="m", usage_class="money", usd=Decimal("0.60")),),
    )

    async with api.client() as client:
        response = await client.get(URL)

    body = response.json()
    assert response.status_code == HTTP_OK
    assert body["next_cursor"] is None
    assert len(body["items"]) == ATTEMPT_COUNT
    item = body["items"][0]
    assert [(r["trigger"], r["usd"]) for r in item["reads"]] == [
        ("attempt_end", "1"),
        ("run_end", "0.58"),
    ]
    assert item["harness_usd"] == "0.60"
    assert item["row_path"] == f"{S0}.plan"
    assert item["role"] == "plan"


async def test_no_harness_money_is_null(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(URL)

    assert response.json()["items"][-1]["harness_usd"] is None


async def test_unknown_run_is_404_problem_json_and_no_bearer_401(api: Api) -> None:
    async with api.client() as client:
        unknown = await client.get(f"/api/v1/runs/{new_id()}/metrics/gateway-reads")
    async with api.client(auth=False) as client:
        anonymous = await client.get(URL)

    assert unknown.status_code == HTTP_NOT_FOUND
    assert unknown.headers["content-type"].startswith(PROBLEM)
    assert anonymous.status_code == HTTP_UNAUTHORIZED


def test_the_router_declares_the_one_operation() -> None:
    operations = {
        (r.path, tuple(sorted(r.methods)))
        for r in run_gateway_reads.router.routes  # type: ignore[attr-defined]
    }
    assert operations == {("/runs/{run_id}/metrics/gateway-reads", ("GET",))}
