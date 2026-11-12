"""The key order `deploy/install.sh` parses on the wire (orchestrator-deploy-folder epic 3, C5;
QA generated 2026-11-12).

`install.sh` reads JSON with sed and awk, never a parser (bash 3.2, no host jq). It splits an
array into rows on each row's first key, and it reads a harness's `setup` as the text after the
`"setup"` key to the end of the row. So the order of the keys is part of the contract
`upgrade`, `setup` and `bmad` depend on:

- `working[]`, `in_engine[]` and a 409's `errors[]` rows begin with `run_id`;
- a `/harnesses` item begins with `name`, and `setup` is its last key, after `lines[]`, whose
  own `ok` fields would otherwise be read as the setup record's;
- a setup failure carries no `ok` of its own.

A schema field moved for any other reason breaks the upgrade's refusals and the setup report
without a single deployment-test fixture noticing, since those fixtures are hand-written JSON.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers_base import setup_record
from orchestrator.api.providers_instance import activity_ports, hold_ports
from orchestrator.application.use_cases.instance_activity import ActivityPorts
from orchestrator.application.use_cases.instance_hold import HoldPorts
from orchestrator.application.use_cases.queue import QueuePorts
from orchestrator.domain.entities.harness import EvaluationLine, Harness
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.writer_fixtures import World, a_world, an_attempt
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.instance_hold import FakeInstanceHoldRepository
from tests.unit.fakes.setup_record import FakeSetupRecord, setup_run
from tests.unit.test_harnesses_router import HARNESSES
from tests.unit.test_harnesses_router import Api as HarnessApi

ACTIVITY = "/api/v1/instance/activity"
HOLD = "/api/v1/instance/hold"
OK = 200
CONFLICT = 409

WORKING_KEYS = ["run_id", "run_label", "path", "kind", "started_at"]
ENGINE_KEYS = ["run_id", "run_label", "status", "park_kind", "queue_reason"]


def ordered(text: str) -> Any:
    """The body with every object as its list of `(key, value)` pairs, in wire order."""
    return json.loads(text, object_pairs_hook=lambda pairs: pairs)


def keys(pairs: list[tuple[str, Any]]) -> list[str]:
    return [key for key, _ in pairs]


def field(pairs: list[tuple[str, Any]], name: str) -> Any:
    return next(value for key, value in pairs if key == name)


def client_for(app: FastAPI, token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://backend-api",
        headers={"Authorization": f"Bearer {token}"},
    )


def a_working_world() -> World:
    world = a_world("running", statuses={"baseline": "running"}, engine_ref={"workflow_id": "wf-1"})
    an_attempt(world, "baseline")
    return world


@pytest.fixture
def instance_app(env: dict[str, str]) -> tuple[FastAPI, World]:
    world = a_working_world()
    app = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
    app.dependency_overrides[activity_ports] = lambda: ActivityPorts(
        queue=QueuePorts(
            engine=world.engine,
            runs=world.ports.runs,
            steps=world.ports.steps,
            clock=world.clock,
            max_active_runs=2,
        ),
        attempts=world.ports.attempts,
        dbos_application_version="7",
    )
    app.dependency_overrides[hold_ports] = lambda: HoldPorts(
        runs=world.ports.runs,
        steps=world.ports.steps,
        attempts=world.ports.attempts,
        holds=FakeInstanceHoldRepository(),
        uow=FakeUnitOfWork(),
        clock=world.clock,
    )
    return app, world


async def test_activity_rows_begin_with_run_id_in_the_order_install_sh_reads(
    instance_app: tuple[FastAPI, World], env: dict[str, str]
) -> None:
    app, world = instance_app
    async with client_for(app, env["ORCHESTRATOR_TOKEN"]) as client:
        response = await client.get(ACTIVITY)

    assert response.status_code == OK, response.text
    body = ordered(response.text)
    working, in_engine = field(body, "working"), field(body, "in_engine")
    assert [keys(row) for row in working] == [WORKING_KEYS]
    assert [keys(row) for row in in_engine] == [ENGINE_KEYS]
    assert field(working[0], "run_id") == str(world.run.id)
    assert field(working[0], "path") == "baseline"
    assert field(in_engine[0], "run_id") == str(world.run.id)
    assert field(body, "dbos_application_version") == "7"


async def test_a_409_names_each_working_step_in_errors_rows_beginning_with_run_id(
    instance_app: tuple[FastAPI, World], env: dict[str, str]
) -> None:
    app, world = instance_app
    async with client_for(app, env["ORCHESTRATOR_TOKEN"]) as client:
        response = await client.post(HOLD, json={"ttl_seconds": 1800, "reason": "upgrade to X"})

    assert response.status_code == CONFLICT, response.text
    errors = field(ordered(response.text), "errors")
    assert [keys(row) for row in errors] == [WORKING_KEYS]
    assert field(errors[0], "run_id") == str(world.run.id)


async def test_a_harness_item_begins_with_name_and_ends_with_setup_after_lines(
    env: dict[str, str],
) -> None:
    api = HarnessApi(env)
    api.harnesses.add(
        Harness(
            name="claude",
            version_pin="1",
            lines=[EvaluationLine(check="cli", ok=True, text="found")],
        )
    )
    run = setup_run(
        scripts=[
            {"name": "10-copy.sh", "exit": 1, "ok": False, "clashes": [], "seconds": 1, "log": "l"}
        ]
    )
    api.app.dependency_overrides[setup_record] = lambda: FakeSetupRecord(run)

    async with api.client() as client:
        response = await client.get(HARNESSES)

    assert response.status_code == OK, response.text
    (item,) = field(ordered(response.text), "items")
    order = keys(item)
    assert order[0] == "name"
    assert order[-1] == "setup"
    assert order.index("lines") < order.index("setup")
    setup = field(item, "setup")
    assert keys(setup)[0] == "at"
    assert keys(setup).count("ok") == 1
    failures = field(setup, "failures")
    assert [keys(row) for row in failures] == [["script", "reason"]]
