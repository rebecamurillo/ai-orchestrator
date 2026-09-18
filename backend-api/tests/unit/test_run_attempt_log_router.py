"""`GET /api/v1/runs/{run_id}/attempts/{attempt_id}/log` (Epic 1, story 1-1) over an ASGI
transport.

Covers every row of the I/O matrix in the intent contract:
- First page (cursor=0, file exists)
- Live follow (poll with last next_cursor)
- Cursor at end
- GC'd log (log_path set, file absent)
- Null log path
- Download, file exists
- Download, GC'd
- Attempt not found
- Wrong run
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from orchestrator.api.providers import run_view_ports
from orchestrator.api.routers import run_attempts as router_module
from orchestrator.api.schemas.run_attempts import LogPageOut
from orchestrator.application.use_cases.run_view_types import RunViewPorts
from orchestrator.domain.entities.attempt import Attempt
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

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_UNAUTHORIZED = 401
PROBLEM_MEDIA_TYPE = "application/problem+json"
CONTENT_TYPE_TEXT = "text/plain"

RUNS = "/api/v1/runs"
NOW = datetime(2026, 9, 16, tzinfo=UTC)

#: A log file path used across tests that supply file content.
LOG_PATH = "/var/run/orchestrator/attempts/attempt-abc.log"

#: Log content: three complete lines plus an incomplete trailing line (forces eof=False on
#: first read) — the incomplete line is not returned until a \n is appended.
LOG_BYTES_PARTIAL = b"line 1\nline 2\nline 3\nincomplete"

#: Log content: three complete lines, nothing trailing (eof=True after first read).
LOG_BYTES_FULL = b"line 1\nline 2\nline 3\n"

#: Unknown UUID for not-found scenarios.
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"


def _attempt(
    *,
    run_id: UUID,
    log_path: str | None = LOG_PATH,
    status: str = "running",
) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=run_id,
        step_run_id=new_id(),
        n=1,
        status=status,  # type: ignore[arg-type]
        log_path=log_path,
    )


class Api:
    """A thin wrapper around the ASGI app for router-level tests."""

    def __init__(
        self, env: dict[str, str], *, raw_by_path: dict[str, bytes | None] | None = None
    ) -> None:
        settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.run_id: UUID = new_id()
        self.attempts = FakeAttemptRepository()
        logs = FakeLogReader(raw_by_path=raw_by_path or {})
        ports = RunViewPorts(
            runs=FakeRunRepository(),
            steps=FakeStepRunRepository(),
            attempts=self.attempts,
            gate_records=FakeGateRecordRepository(),
            projects=FakeProjectRepository(),
            repositories=FakeRepositoryRepository(),
            logs=logs,
            clock=FakeClock(NOW),
        )
        app = create_app(settings)
        app.dependency_overrides[run_view_ports] = lambda: ports
        self._app = app
        self._token = env["ORCHESTRATOR_TOKEN"]

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self._app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self._token}"},
        )

    def anonymous(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self._app, raise_app_exceptions=False),
            base_url="http://backend-api",
        )

    def url(self, attempt_id: UUID | str) -> str:
        return f"{RUNS}/{self.run_id}/attempts/{attempt_id}/log"


# ── Structural test ──────────────────────────────────────────────────────────


def test_the_router_declares_exactly_one_operation() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert routes == [(["GET"], "/runs/{run_id}/attempts/{attempt_id}/log")]
    for route in router_module.router.routes:
        assert route.dependencies == []


def test_log_page_out_schema_fields() -> None:
    """LogPageOut carries exactly lines, next_cursor and eof."""
    cursor = 42  # any non-zero byte offset
    page = LogPageOut(lines=["a", "b"], next_cursor=cursor, eof=False)
    assert page.lines == ["a", "b"]
    assert page.next_cursor == cursor
    assert page.eof is False


# ── First page ───────────────────────────────────────────────────────────────


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env, raw_by_path={LOG_PATH: LOG_BYTES_PARTIAL})


async def test_first_page_returns_complete_lines_and_eof_false(api: Api) -> None:
    """cursor=0 on a file with an incomplete trailing line → eof=False, lines non-empty."""
    attempt = _attempt(run_id=api.run_id)
    api.attempts.add(attempt)

    async with api.client() as client:
        resp = await client.get(api.url(attempt.id), params={"cursor": 0, "limit": 200})

    assert resp.status_code == HTTP_OK
    body = resp.json()
    assert body["lines"] == ["line 1", "line 2", "line 3"]
    assert body["next_cursor"] == len(b"line 1\nline 2\nline 3\n")
    assert body["eof"] is False


async def test_response_model_keys_are_lines_next_cursor_eof(api: Api) -> None:
    """The JSON object has exactly the three LogPageOut fields."""
    attempt = _attempt(run_id=api.run_id)
    api.attempts.add(attempt)

    async with api.client() as client:
        resp = await client.get(api.url(attempt.id))

    assert resp.status_code == HTTP_OK
    assert set(resp.json()) == {"lines", "next_cursor", "eof"}


# ── Live follow (poll with last next_cursor) ─────────────────────────────────


async def test_live_follow_returns_only_new_lines(api: Api) -> None:
    """Polling with the previous next_cursor returns only newly appended bytes."""
    attempt = _attempt(run_id=api.run_id)
    api.attempts.add(attempt)

    # cursor past "line 1\n"
    cursor_after_line1 = len(b"line 1\n")

    async with api.client() as client:
        resp = await client.get(api.url(attempt.id), params={"cursor": cursor_after_line1})

    assert resp.status_code == HTTP_OK
    body = resp.json()
    assert body["lines"] == ["line 2", "line 3"]
    assert body["next_cursor"] > cursor_after_line1


# ── Cursor at end ────────────────────────────────────────────────────────────


@pytest.fixture
def full_api(env: dict[str, str]) -> Api:
    return Api(env, raw_by_path={LOG_PATH: LOG_BYTES_FULL})


async def test_cursor_at_end_returns_empty_and_eof_true(full_api: Api) -> None:
    attempt = _attempt(run_id=full_api.run_id)
    full_api.attempts.add(attempt)

    cursor_at_end = len(LOG_BYTES_FULL)

    async with full_api.client() as client:
        resp = await client.get(full_api.url(attempt.id), params={"cursor": cursor_at_end})

    assert resp.status_code == HTTP_OK
    body = resp.json()
    assert body["lines"] == []
    assert body["next_cursor"] == cursor_at_end
    assert body["eof"] is True


# ── GC'd log ─────────────────────────────────────────────────────────────────


@pytest.fixture
def gc_api(env: dict[str, str]) -> Api:
    """No file in raw_by_path → every path is GC'd."""
    return Api(env, raw_by_path={})


async def test_gcd_log_returns_200_with_gc_message(gc_api: Api) -> None:
    attempt = _attempt(run_id=gc_api.run_id)
    gc_api.attempts.add(attempt)

    async with gc_api.client() as client:
        resp = await client.get(gc_api.url(attempt.id))

    assert resp.status_code == HTTP_OK
    body = resp.json()
    assert body["lines"] == ["log no longer on disk"]
    assert body["next_cursor"] == 0
    assert body["eof"] is True


# ── Null log path ─────────────────────────────────────────────────────────────


@pytest.fixture
def no_log_api(env: dict[str, str]) -> Api:
    return Api(env)


async def test_null_log_path_returns_empty_eof_true(no_log_api: Api) -> None:
    attempt = _attempt(run_id=no_log_api.run_id, log_path=None)
    no_log_api.attempts.add(attempt)

    async with no_log_api.client() as client:
        resp = await client.get(no_log_api.url(attempt.id))

    assert resp.status_code == HTTP_OK
    body = resp.json()
    assert body["lines"] == []
    assert body["next_cursor"] == 0
    assert body["eof"] is True


# ── Download, file exists ────────────────────────────────────────────────────


async def test_download_file_exists_content_type_and_disposition(api: Api) -> None:
    attempt = _attempt(run_id=api.run_id)
    api.attempts.add(attempt)

    async with api.client() as client:
        resp = await client.get(api.url(attempt.id), params={"download": "true"})

    assert resp.status_code == HTTP_OK
    assert resp.headers["content-type"].startswith(CONTENT_TYPE_TEXT)
    disposition = resp.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert f"{attempt.id}.log" in disposition


async def test_download_file_exists_body_is_raw_bytes(api: Api) -> None:
    attempt = _attempt(run_id=api.run_id)
    api.attempts.add(attempt)

    async with api.client() as client:
        resp = await client.get(api.url(attempt.id), params={"download": "true"})

    assert resp.content == LOG_BYTES_PARTIAL


# ── Download, GC'd ───────────────────────────────────────────────────────────


async def test_download_gcd_returns_200_text_plain(gc_api: Api) -> None:
    attempt = _attempt(run_id=gc_api.run_id)
    gc_api.attempts.add(attempt)

    async with gc_api.client() as client:
        resp = await client.get(gc_api.url(attempt.id), params={"download": "true"})

    assert resp.status_code == HTTP_OK
    assert resp.headers["content-type"].startswith(CONTENT_TYPE_TEXT)
    assert b"log no longer on disk" in resp.content
    # GC'd response is a status message, not a file attachment
    assert "attachment" not in resp.headers.get("content-disposition", "")


# ── Null log path + download ──────────────────────────────────────────────────


async def test_null_log_path_download_returns_empty_text_plain(no_log_api: Api) -> None:
    """When log_path is None and ?download=true, the response is an empty text/plain body."""
    attempt = _attempt(run_id=no_log_api.run_id, log_path=None)
    no_log_api.attempts.add(attempt)

    async with no_log_api.client() as client:
        resp = await client.get(no_log_api.url(attempt.id), params={"download": "true"})

    assert resp.status_code == HTTP_OK
    assert resp.headers["content-type"].startswith(CONTENT_TYPE_TEXT)
    assert resp.content == b""


# ── Attempt not found ─────────────────────────────────────────────────────────


async def test_unknown_attempt_is_a_404(api: Api) -> None:
    async with api.client() as client:
        resp = await client.get(api.url(UNKNOWN_ID))

    assert resp.status_code == HTTP_NOT_FOUND
    assert resp.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


# ── Wrong run ────────────────────────────────────────────────────────────────


async def test_attempt_from_different_run_is_a_404(api: Api) -> None:
    other_run_id = new_id()
    attempt = _attempt(run_id=other_run_id)  # belongs to a different run
    api.attempts.add(attempt)

    async with api.client() as client:
        resp = await client.get(api.url(attempt.id))

    assert resp.status_code == HTTP_NOT_FOUND
    assert resp.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


# ── Auth ─────────────────────────────────────────────────────────────────────


async def test_without_the_bearer_it_is_a_401(api: Api) -> None:
    attempt = _attempt(run_id=api.run_id)
    api.attempts.add(attempt)

    async with api.anonymous() as client:
        resp = await client.get(api.url(attempt.id))

    assert resp.status_code == HTTP_UNAUTHORIZED
