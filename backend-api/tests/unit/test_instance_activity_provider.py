"""`activity_ports` (SPEC CAP-3, AD-30): the version comes from settings, and nothing commits.

The router tests override this provider, so this is the only place its own wiring is read.
"""

from __future__ import annotations

from fastapi import FastAPI, Request

from orchestrator.api.providers_instance import activity_ports
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.engine import FakeWorkflowEngine


class _Session:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def rollback(self) -> None:
        self.calls.append("rollback")

    def close(self) -> None:
        self.calls.append("close")

    def commit(self) -> None:
        self.calls.append("commit")


def _request(env: dict[str, str], session: _Session) -> Request:
    app = FastAPI()
    settings = Settings(**{key.lower(): value for key, value in env.items()})
    app.state.settings = settings
    app.state.session_factory = lambda: session
    app.state.engine = FakeWorkflowEngine()
    return Request({"type": "http", "app": app})


def test_the_version_is_read_from_settings_and_the_session_is_never_committed(
    env: dict[str, str],
) -> None:
    session = _Session()
    request = _request({**env, "DBOS_APPLICATION_VERSION": "2"}, session)

    produced = list(activity_ports(request))

    assert len(produced) == 1
    assert produced[0].dbos_application_version == "2"
    assert produced[0].queue.max_active_runs == request.app.state.settings.max_active_runs
    assert session.calls == ["rollback", "close"]
