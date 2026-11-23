"""`GET /runs/{id}/graph` carries step identity and run order; the new fields are emitted
optional (story 4, AD-40)."""

from __future__ import annotations

import pytest

from orchestrator.api.schemas.graph import RunGraphOut, RunNodeOut
from orchestrator.api.schemas.run_views import StepRowOut
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ids import new_id
from tests.unit.test_run_graph_router import RUNS, Api, a_row, a_run

HTTP_OK = 200


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


async def test_graph_body_carries_identity_and_run_order(api: Api) -> None:
    run = a_run()
    api.runs.add(run)
    build = a_row(run, "build", seq=2, status="done").model_copy(update={"kind": "agent"})
    api.steps.add_many([a_row(run, "sync", seq=1, status="done"), build])
    api.ports.attempts.add(  # type: ignore[attr-defined]
        Attempt(id=new_id(), run_id=run.id, step_run_id=build.id, n=1, status="done")
    )

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/graph")

    assert response.status_code == HTTP_OK
    body = response.json()
    root, sync, node = body["nodes"]
    assert root["seq"] is None
    assert sync["seq"] == 1
    assert sync["attempt_n"] is None
    assert sync["attempt_ns"] == []
    assert (node["seq"], node["attempt_n"], node["attempt_ns"]) == (2, 1, [1])
    (frame,) = body["run_order"]
    assert frame["frame"] == "root"
    assert [r["phase"] for r in frame["rows"]] == ["BEFORE", "AGENT"]
    assert set(frame["rows"][0]) == {"seq", "path", "label", "kind", "token", "phase"}


@pytest.mark.parametrize(
    ("model", "fields"),
    [
        (RunNodeOut, ("seq", "attempt_n", "attempt_ns")),
        (RunGraphOut, ("run_order",)),
        (StepRowOut, ("attempt_ns",)),
    ],
)
def test_new_fields_are_optional_without_a_schema_default(
    model: type, fields: tuple[str, ...]
) -> None:
    schema = model.model_json_schema()
    for field in fields:
        assert "default" not in schema["properties"][field]
        assert field not in schema.get("required", [])
