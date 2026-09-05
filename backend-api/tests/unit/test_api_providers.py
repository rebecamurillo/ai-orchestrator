"""Where a request gets its ports, and what happens when it cannot.

Two claims. The first is that `project_ports` builds the ports on one transaction: the
repository sits on the session the unit of work opened, and leaving the request without a
commit rolls that session back — so a use case that raised, or a response model that
refused the payload, persists nothing.

The second is the failure mode. An application built without its adapters — the shape
`tools/export_openapi.py` uses, and the shape a misconfigured process would have — must
answer a problem document with a 500, not an `AssertionError` and not a `TypeError` from
calling `None`. `assert` disappears under `python -O`, so a check that used one would not
be a check at all.
"""

from __future__ import annotations

from typing import Annotated, Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI

from orchestrator.api.errors import PROBLEM_MEDIA_TYPE, install_error_handlers
from orchestrator.api.providers import CRYPTO, SESSION_FACTORY, project_ports
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.crypto import FernetCrypto
from orchestrator.infrastructure.db import SQLAlchemyProjectRepository
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app, crypto_factory
from tests.unit.fakes.crypto import FakeCrypto

HTTP_OK = 200
HTTP_SERVER_ERROR = 500

#: Two requests, two sessions.
TWO = 2


class RecordingSession:
    """A stand-in for `sqlalchemy.orm.Session`: it records, it does not connect."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def commit(self) -> None:
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")

    def close(self) -> None:
        self.calls.append("close")


class RecordingSessionFactory:
    def __init__(self) -> None:
        self.sessions: list[RecordingSession] = []

    def __call__(self) -> RecordingSession:
        session = RecordingSession()
        self.sessions.append(session)
        return session


def probe_app(*, session_factory: Any = None, crypto: Any = None) -> tuple[FastAPI, list[Any]]:
    """A one-route application whose only job is to receive the ports and report them."""
    app = FastAPI()
    install_error_handlers(app)
    setattr(app.state, SESSION_FACTORY, session_factory)
    setattr(app.state, CRYPTO, crypto)
    captured: list[Any] = []

    @app.get("/probe")
    def probe(ports: Annotated[ProjectPorts, Depends(project_ports)]) -> dict[str, bool]:
        captured.append(ports)
        return {"ok": True}

    @app.get("/probe-commit")
    def probe_commit(ports: Annotated[ProjectPorts, Depends(project_ports)]) -> dict[str, bool]:
        ports.uow.commit()
        return {"ok": True}

    @app.get("/probe-raises")
    def probe_raises(ports: Annotated[ProjectPorts, Depends(project_ports)]) -> dict[str, bool]:
        raise RuntimeError("the use case failed")

    return app, captured


async def call(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        return await client.get(path)


@pytest.fixture
def factory() -> RecordingSessionFactory:
    return RecordingSessionFactory()


# ── the ports a request receives ─────────────────────────────────────────────


async def test_the_repository_sits_on_the_session_the_unit_of_work_opened(
    factory: RecordingSessionFactory,
) -> None:
    """A repository on any other session would write outside the caller's transaction."""
    crypto = FakeCrypto()
    app, captured = probe_app(session_factory=factory, crypto=lambda: crypto)

    response = await call(app, "/probe")

    assert response.status_code == HTTP_OK
    (ports,) = captured
    assert isinstance(ports.projects, SQLAlchemyProjectRepository)
    assert ports.projects._session is factory.sessions[0]


async def test_the_crypto_comes_from_the_factory_on_the_application_state(
    factory: RecordingSessionFactory,
) -> None:
    """The adapter is built on first use, so a placeholder key does not stop start-up."""
    crypto = FakeCrypto()
    built: list[int] = []
    app, captured = probe_app(session_factory=factory, crypto=lambda: (built.append(1), crypto)[1])

    await call(app, "/probe")

    assert captured[0].crypto is crypto
    assert built == [1]


async def test_the_clock_is_the_wall_clock_adapter(factory: RecordingSessionFactory) -> None:
    app, captured = probe_app(session_factory=factory, crypto=FakeCrypto)

    await call(app, "/probe")

    assert isinstance(captured[0].clock, SystemClock)


async def test_a_request_that_never_commits_rolls_its_session_back(
    factory: RecordingSessionFactory,
) -> None:
    app, _ = probe_app(session_factory=factory, crypto=FakeCrypto)

    await call(app, "/probe")

    assert factory.sessions[0].calls == ["rollback", "close"]


async def test_a_request_that_commits_keeps_its_work(
    factory: RecordingSessionFactory,
) -> None:
    app, _ = probe_app(session_factory=factory, crypto=FakeCrypto)

    await call(app, "/probe-commit")

    assert factory.sessions[0].calls == ["commit", "close"]


async def test_a_failing_request_persists_nothing(factory: RecordingSessionFactory) -> None:
    app, _ = probe_app(session_factory=factory, crypto=FakeCrypto)

    response = await call(app, "/probe-raises")

    assert response.status_code == HTTP_SERVER_ERROR
    assert factory.sessions[0].calls == ["rollback", "close"]


async def test_each_request_gets_its_own_session(factory: RecordingSessionFactory) -> None:
    app, _ = probe_app(session_factory=factory, crypto=FakeCrypto)

    await call(app, "/probe")
    await call(app, "/probe")

    assert len(factory.sessions) == TWO


# ── the application that was built without its adapters ──────────────────────


#: Which adapter each case leaves out, and which one the refusal must name first. A
#: factory is built inside the test rather than here: a value in the decorator is
#: constructed once, at collection, and then shared by every run of the case.
MISSING_ADAPTER_CASES = [
    pytest.param(False, True, SESSION_FACTORY, id="no-session-factory"),
    pytest.param(True, False, CRYPTO, id="no-crypto"),
    pytest.param(False, False, SESSION_FACTORY, id="neither"),
]


@pytest.mark.parametrize(("has_session_factory", "has_crypto", "missing"), MISSING_ADAPTER_CASES)
async def test_a_missing_adapter_answers_a_problem_document_and_not_an_assertion(
    has_session_factory: bool, has_crypto: bool, missing: str
) -> None:
    session_factory = RecordingSessionFactory() if has_session_factory else None
    app, _ = probe_app(session_factory=session_factory, crypto=FakeCrypto if has_crypto else None)

    response = await call(app, "/probe")

    assert response.status_code == HTTP_SERVER_ERROR
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["title"] == "internal server error"
    # the body says nothing; the message that names the wiring goes to the log
    assert missing not in response.text
    with pytest.raises(RuntimeError, match=missing):
        next(project_ports(_request_for(app)))


def test_the_refusal_names_the_adapter_that_is_missing() -> None:
    """ "It broke" is not actionable; the log line has to say which wiring is absent."""
    app, _ = probe_app()

    with pytest.raises(RuntimeError, match=SESSION_FACTORY):
        next(project_ports(_request_for(app)))


def _request_for(app: FastAPI) -> Any:
    class Probe:
        def __init__(self, application: FastAPI) -> None:
            self.app = application

    return Probe(app)


# ── what the composition root stores ─────────────────────────────────────────


def test_create_app_stores_the_adapters_the_providers_read(env: dict[str, str]) -> None:
    factory = RecordingSessionFactory()
    crypto = FakeCrypto()

    app = create_app(Settings(), session_factory=factory, crypto=lambda: crypto)

    assert getattr(app.state, SESSION_FACTORY) is factory
    assert getattr(app.state, CRYPTO)() is crypto


def test_an_application_built_without_them_still_builds(env: dict[str, str]) -> None:
    """`tools/export_openapi.py` builds one: it reads routes and performs no I/O (AD-3)."""
    app = create_app(Settings())

    assert getattr(app.state, SESSION_FACTORY) is None
    assert getattr(app.state, CRYPTO) is None


# ── the deferred key ─────────────────────────────────────────────────────────


def test_the_crypto_factory_refuses_the_contract_placeholder_only_on_first_use(
    env: dict[str, str],
) -> None:
    """`.env.example` carries `change-me-fernet-key`, and `main()` is called with it.

    Building the adapter eagerly would turn a misconfigured instance into a process that
    cannot start at all — including in `tests/unit/test_logging.py`, which calls `main()`.
    """
    build = crypto_factory(Settings())

    with pytest.raises(ValueError, match="ORCHESTRATOR_SECRET_KEY"):
        build()


def test_the_crypto_factory_builds_the_fernet_adapter_once(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORCHESTRATOR_SECRET_KEY", Fernet.generate_key().decode())

    build = crypto_factory(Settings())

    assert isinstance(build(), FernetCrypto)
    assert build() is build()
