"""`alert.chat_thread` on the Run detail (story 3-3): the stop's thread, `{provider, state,
error}`, whatever its state, or `null` when the stop has none.

The thread is read by `get_by_stop(run.id, run.park_seq)`. The route runs over an ASGI
transport with the shared fakes injected; the provider test proves the real adapter is wired.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import run_view_ports
from orchestrator.api.schemas.run_alert import AlertOut, ChatThreadOut
from orchestrator.application.use_cases.run_view_types import (
    Alert,
    ChatThreadNote,
    RunViewPorts,
)
from orchestrator.application.use_cases.run_views_alert import build_alert
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db import SQLAlchemyChatThreadRepository
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.chat_thread import FakeChatThreadRepository
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
RUNS = "/api/v1/runs"


def a_run(**overrides: Any) -> Run:
    fields: dict[str, Any] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "needs_you",
        "budget_usd": Decimal("10"),
        "park_kind": "blocked",
        "park_path": "stories[0].build",
        "park_reason": "Which schema?",
        "park_seq": 3,
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)


def a_thread(run: Run, **overrides: Any) -> ChatThread:
    fields: dict[str, Any] = {
        "id": new_id(),
        "run_id": run.id,
        "park_seq": run.park_seq,
        "park_kind": "blocked",
        "provider": "mattermost",
        "channel_id": "c1",
        "ref": None,
        "cursor": None,
        "state": "failed",
        "error": "403 bot not in channel",
        "last_reminded_at": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    fields.update(overrides)
    return ChatThread(**fields)


class Api:
    def __init__(self, env: dict[str, str], *, wired: bool = True) -> None:
        self.runs = FakeRunRepository()
        self.threads = FakeChatThreadRepository(self.runs)
        self.ports = RunViewPorts(
            runs=self.runs,
            steps=FakeStepRunRepository(),
            attempts=FakeAttemptRepository(),
            gate_records=FakeGateRecordRepository(),
            projects=FakeProjectRepository(),
            repositories=FakeRepositoryRepository(),
            logs=FakeLogReader(),
            clock=FakeClock(NOW),
            chat_threads=self.threads if wired else None,
        )
        self.app: FastAPI = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
        self.app.dependency_overrides[run_view_ports] = lambda: self.ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    async def alert(self, run: Run) -> Any:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        ) as client:
            response = await client.get(f"{RUNS}/{run.id}/detail")
        assert response.status_code == httpx.codes.OK
        return response.json()["alert"]


async def test_a_failed_thread_shows_its_state_and_error(env: dict[str, str]) -> None:
    api = Api(env)
    run = a_run()
    api.runs.add(run)
    api.threads.add(a_thread(run))

    alert = await api.alert(run)

    assert alert["chat_thread"] == {
        "provider": "mattermost",
        "state": "failed",
        "error": "403 bot not in channel",
    }


async def test_an_open_thread_shows_its_state_and_no_error(env: dict[str, str]) -> None:
    api = Api(env)
    run = a_run()
    api.runs.add(run)
    api.threads.add(a_thread(run, provider="slack", state="open", ref="1.2", error=None))

    alert = await api.alert(run)

    assert alert["chat_thread"] == {"provider": "slack", "state": "open", "error": None}


@pytest.mark.parametrize("wired", [True, False])
async def test_a_stop_with_no_thread_reads_null(env: dict[str, str], wired: bool) -> None:
    api = Api(env, wired=wired)
    run = a_run()
    api.runs.add(run)
    api.threads.add(a_thread(run, park_seq=2))

    alert = await api.alert(run)

    assert alert["chat_thread"] is None


def test_build_alert_carries_the_thread_note_whatever_its_state() -> None:
    run = a_run()
    for state in ("posting", "open", "closed", "failed"):
        alert = build_alert(
            run,
            None,
            row_kind=None,
            rows=(),
            park_row=None,
            attempts_by_row={},
            thread=a_thread(run, state=state),
        )
        assert alert is not None
        assert alert.chat_thread == ChatThreadNote(
            provider="mattermost", state=state, error="403 bot not in channel"
        )


def test_build_alert_without_a_thread_carries_none() -> None:
    alert = build_alert(a_run(), None, row_kind=None, rows=(), park_row=None, attempts_by_row={})

    assert alert is not None
    assert alert.chat_thread is None


def test_the_schema_maps_the_note_and_drops_its_default() -> None:
    note = ChatThreadNote(provider="slack", state="posting", error=None)
    alert = Alert(token="BLK", reason=None, park_kind="blocked", chat_thread=note)

    out = AlertOut.of(alert)

    assert out.chat_thread == ChatThreadOut(provider="slack", state="posting", error=None)
    assert "default" not in AlertOut.model_json_schema()["properties"]["chat_thread"]


def test_the_provider_wires_the_thread_repository(env: dict[str, str]) -> None:
    class Session:
        def commit(self) -> None: ...

        def rollback(self) -> None: ...

        def close(self) -> None: ...

    class Probe:
        def __init__(self, application: FastAPI) -> None:
            self.app = application

    app = create_app(Settings(), session_factory=Session)

    ports = next(run_view_ports(Probe(app)))  # type: ignore[arg-type]

    assert isinstance(ports.chat_threads, SQLAlchemyChatThreadRepository)
