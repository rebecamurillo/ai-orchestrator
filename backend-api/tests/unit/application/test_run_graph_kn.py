"""k/n computation on run-graph groups (story 1-5, AD-15).

`k` = count of `done` members; `n` = count of members with status != 'skipped'.

Tested in two layers:
  1. Pure application: `build_run_graph` group objects carry k/n.
  2. HTTP round-trip: `GET /runs/{run_id}/graph` serialises k/n on to `RunGroupOut`.

TDD: written first — all tests must fail before Group/RunGroupOut changes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import run_view_ports
from orchestrator.application.graph import build_run_graph
from orchestrator.application.use_cases.run_view_types import RunViewPorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
RUNS = "/api/v1/runs"


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("10"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_row(run: Run, path: str, *, seq: int, status: str = "planned") -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run.id,
        seq=seq,
        path=path,
        label=path.rsplit(".", maxsplit=1)[-1],
        kind="shell",
        gate="deterministic",
        status=status,  # type: ignore[arg-type]
    )


# ── pure application layer ──────────────────────────────────────────────────


def test_all_done_group_k_equals_n_equals_total() -> None:
    """All-done group: k = n = total member count."""
    run = a_run()
    rows = [
        a_row(run, "epics[0].stories[0].sync", seq=1, status="done"),
        a_row(run, "epics[0].stories[0].build", seq=2, status="done"),
        a_row(run, "epics[0].stories[0].verify", seq=3, status="done"),
    ]
    graph = build_run_graph(rows, run)
    group = next(g for g in graph.groups if g.id == "epics[0].stories[0]")
    expected_done = 3
    expected_non_skipped = 3
    assert group.k == expected_done
    assert group.n == expected_non_skipped


def test_mixed_group_k_is_done_count_n_is_total_minus_skipped() -> None:
    """Mixed group: k = done count, n = total - skipped."""
    run = a_run()
    rows = [
        a_row(run, "epics[0].stories[0].sync", seq=1, status="done"),
        a_row(run, "epics[0].stories[0].build", seq=2, status="done"),
        a_row(run, "epics[0].stories[0].verify", seq=3, status="skipped"),
        a_row(run, "epics[0].stories[0].push", seq=4, status="done"),
        a_row(run, "epics[0].stories[0].link", seq=5, status="planned"),
    ]
    graph = build_run_graph(rows, run)
    group = next(g for g in graph.groups if g.id == "epics[0].stories[0]")
    expected_done = 3  # sync, build, push are done
    expected_non_skipped = 4  # 5 total - 1 skipped
    assert group.k == expected_done
    assert group.n == expected_non_skipped


def test_all_skipped_group_k_and_n_are_zero() -> None:
    """All-skipped group: k = 0, n = 0."""
    run = a_run()
    rows = [
        a_row(run, "epics[0].stories[0].sync", seq=1, status="skipped"),
        a_row(run, "epics[0].stories[0].build", seq=2, status="skipped"),
    ]
    graph = build_run_graph(rows, run)
    group = next(g for g in graph.groups if g.id == "epics[0].stories[0]")
    assert group.k == 0
    assert group.n == 0


# ── HTTP round-trip ─────────────────────────────────────────────────────────


class Api:
    def __init__(self, env: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.ports = RunViewPorts(
            runs=self.runs,
            steps=self.steps,
            attempts=FakeAttemptRepository(),
            gate_records=FakeGateRecordRepository(),
            projects=FakeProjectRepository(),
            repositories=FakeRepositoryRepository(),
            logs=FakeLogReader(),
            clock=FakeClock(NOW),
        )
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[run_view_ports] = lambda: self.ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


async def test_k_and_n_present_on_run_group_out_http_round_trip(api: Api) -> None:
    """k and n are serialised onto RunGroupOut through GET /runs/{run_id}/graph."""
    run = a_run()
    api.runs.add(run)
    api.steps.add_many(
        [
            a_row(run, "epics[0].stories[0].sync", seq=1, status="done"),
            a_row(run, "epics[0].stories[0].build", seq=2, status="done"),
            a_row(run, "epics[0].stories[0].verify", seq=3, status="done"),
            a_row(run, "epics[0].stories[0].push", seq=4, status="skipped"),
            a_row(run, "epics[0].stories[0].link", seq=5, status="planned"),
        ]
    )

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/graph")

    assert response.status_code == 200  # noqa: PLR2004
    body = response.json()
    story_group = next(g for g in body["groups"] if g["id"] == "epics[0].stories[0]")
    expected_k = 3  # sync, build, verify done
    expected_n = 4  # 5 total - 1 skipped (link is planned, not skipped)
    assert story_group["k"] == expected_k
    assert story_group["n"] == expected_n


def test_cancelled_run_group_kn_computed_from_member_statuses() -> None:
    """Cancelled run: k/n are computed from member statuses even when group status is None."""
    run = a_run(status="cancelled")
    rows = [
        a_row(run, "epics[0].stories[0].sync", seq=1, status="done"),
        a_row(run, "epics[0].stories[0].build", seq=2, status="running"),
        a_row(run, "epics[0].stories[0].verify", seq=3, status="planned"),
    ]
    graph = build_run_graph(rows, run)
    group = next(g for g in graph.groups if g.id == "epics[0].stories[0]")
    # group.status is None for a cancelled run; k/n still reflect member statuses
    expected_k = 1  # only sync is done
    expected_n = 3  # none are skipped (running and planned both count toward n)
    assert group.status is None
    assert group.k == expected_k
    assert group.n == expected_n
