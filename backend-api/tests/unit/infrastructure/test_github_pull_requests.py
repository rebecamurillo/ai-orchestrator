"""`infrastructure/github/pull_requests.py` — epic 9 story 1, AC7."""

from __future__ import annotations

import httpx
import pytest
from structlog.testing import capture_logs

from orchestrator.domain.ports.pull_requests import PullRequests
from orchestrator.infrastructure.github.pull_requests import GitHubPullRequests

TOKEN = "tok-test-value"


def adapter(handler: httpx.MockTransport) -> GitHubPullRequests:
    return GitHubPullRequests(TOKEN, transport=handler)


def answering(status: int, content: str | bytes) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, content=content))


def test_it_satisfies_the_port() -> None:
    assert isinstance(adapter(answering(200, "[]")), PullRequests)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('[{"merged_at": "2026-11-20T10:00:00Z"}]', True),
        ('[{"merged_at": null}, {"merged_at": "2026-11-20T10:00:00Z"}]', True),
        ('[{"merged_at": null}]', False),
        ("[]", False),
    ],
)
def test_a_readable_answer_is_true_or_false(body: str, expected: bool) -> None:
    assert adapter(answering(200, body)).merged("o", "a", "feat/x") is expected


def test_the_request_carries_the_token_the_media_type_and_the_query() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    adapter(httpx.MockTransport(handler)).merged("o", "a", "feat/x")

    (request,) = seen
    assert request.method == "GET"
    assert request.url.scheme == "https"
    assert request.url.host == "api.github.com"
    assert request.url.path == "/repos/o/a/pulls"
    assert dict(request.url.params) == {"state": "closed", "head": "o:feat/x", "per_page": "100"}
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.headers["Accept"] == "application/vnd.github+json"


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow", request=request)


@pytest.mark.parametrize(
    "transport",
    [
        answering(500, "[]"),
        answering(404, "{}"),
        answering(200, "not json"),
        answering(200, '{"merged_at": "x"}'),
        answering(200, "[1]"),
        httpx.MockTransport(_timeout),
    ],
)
def test_anything_unreadable_is_none_and_logged_without_the_token(
    transport: httpx.MockTransport,
) -> None:
    with capture_logs() as logs:
        assert adapter(transport).merged("o", "a", "feat/x") is None

    (event,) = [e for e in logs if e["event"] == "pull_request_check_unreadable"]
    assert (event["owner"], event["repo"], event["head"]) == ("o", "a", "feat/x")
    assert "status" in event
    assert TOKEN not in repr(logs)


def test_the_token_is_not_in_the_adapters_repr() -> None:
    assert TOKEN not in repr(adapter(answering(200, "[]")))
