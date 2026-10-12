"""The webhook notifier: bodies, signature, best-effort delivery, and which adapter is wired."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr
from structlog.testing import capture_logs

from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.notifier import Notifier, RunNotification
from orchestrator.infrastructure.notify import NullNotifier, WebhookNotifier, build_notifier
from orchestrator.infrastructure.notify.format import (
    SIGNATURE_HEADER,
    SLACK_REASON_LIMIT,
    event_payload,
    render,
    run_url,
    sign,
    slack_text,
)
from orchestrator.infrastructure.settings import Settings

AT = datetime(2026, 10, 12, 8, 30, 15, tzinfo=UTC)
HOOK = "https://hooks.example.test/T000/B000"


def an_event(**over: object) -> RunNotification:
    fields: dict[str, object] = {
        "run_id": new_id(),
        "project": "Les Martines",
        "repository": "app",
        "template": "initiative-hub-story",
        "status": "needs_you",
        "park_kind": "blocked",
        "reason": "agent is blocked on a missing secret",
        "step_path": "stories[0].build",
        "attempt_id": new_id(),
        "spend_usd": Decimal("1.50"),
        "occurred_at": AT,
    }
    fields.update(over)
    return RunNotification(**fields)  # type: ignore[arg-type]


def test_the_json_body_carries_every_field_and_the_run_link() -> None:
    event = an_event()

    body = json.loads(render(event, "json", "https://orch.example.test/"))

    assert body == {
        "run_id": str(event.run_id),
        "project": "Les Martines",
        "repository": "app",
        "template": "initiative-hub-story",
        "status": "needs_you",
        "park_kind": "blocked",
        "reason": "agent is blocked on a missing secret",
        "step_path": "stories[0].build",
        "attempt_id": str(event.attempt_id),
        "spend_usd": "1.50",
        "occurred_at": "2026-10-12T08:30:15Z",
        "url": f"https://orch.example.test/workflows/{event.run_id}",
    }


def test_a_blank_public_base_url_omits_the_link() -> None:
    event = an_event(attempt_id=None)

    payload = event_payload(event, run_url("  ", event))

    assert "url" not in payload
    assert payload["attempt_id"] is None


def test_the_slack_body_is_one_compact_message() -> None:
    event = an_event()

    body = json.loads(render(event, "slack", "https://orch.example.test"))

    assert list(body) == ["text"]
    assert body["text"] == (
        "Run needs you: Les Martines / app | initiative-hub-story | blocked | stories[0].build"
        " | agent is blocked on a missing secret | $1.50"
        f" | https://orch.example.test/workflows/{event.run_id}"
    )


def test_a_terminal_slack_message_without_park_fields_stays_short_and_truncates_reasons() -> None:
    event = an_event(
        status="failed", park_kind=None, step_path=None, reason="x" * (SLACK_REASON_LIMIT + 50)
    )

    text = slack_text(event, None)

    assert text.startswith("Run failed: Les Martines / app | initiative-hub-story | ")
    assert text.endswith(f"{'x' * SLACK_REASON_LIMIT} | $1.50")


def test_a_slack_message_with_no_reason_has_none_to_print() -> None:
    assert slack_text(an_event(reason=None), None).endswith("stories[0].build | $1.50")


def test_the_signature_is_the_hmac_of_the_exact_body() -> None:
    body = b'{"a":1}'

    assert sign("s3cret", body) == "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()


def captured(secret: str = "", fmt: str = "json") -> tuple[WebhookNotifier, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    notifier = WebhookNotifier(
        url=HOOK,
        secret=secret,
        fmt=fmt,  # type: ignore[arg-type]
        base_url="",
        client=httpx.Client(transport=httpx.MockTransport(respond)),
        submit=lambda fn, *args: fn(*args),
    )
    return notifier, requests


def test_a_secret_signs_the_body_that_was_sent() -> None:
    notifier, requests = captured(secret="s3cret")

    notifier.notify(an_event())

    [request] = requests
    assert str(request.url) == HOOK
    assert request.headers[SIGNATURE_HEADER] == sign("s3cret", request.content)


def test_no_secret_means_no_signature_header() -> None:
    notifier, requests = captured()

    notifier.notify(an_event())

    assert SIGNATURE_HEADER not in requests[0].headers


@pytest.mark.parametrize(
    "response",
    [httpx.Response(500), httpx.ConnectError("refused")],
    ids=["status", "transport"],
)
def test_a_delivery_failure_is_logged_and_never_raised(response: object) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if isinstance(response, Exception):
            raise response
        return response  # type: ignore[return-value]

    notifier = WebhookNotifier(
        url=HOOK,
        secret="",
        fmt="json",
        base_url="",
        client=httpx.Client(transport=httpx.MockTransport(respond)),
        submit=lambda fn, *args: fn(*args),
    )

    with capture_logs() as logs:
        notifier.notify(an_event())

    assert [(line["event"], line["log_level"]) for line in logs] == [("notify_failed", "warning")]


def test_the_default_worker_delivers_off_the_calling_thread() -> None:
    delivered = []
    notifier = WebhookNotifier(
        url=HOOK,
        secret="",
        fmt="json",
        base_url="",
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: delivered.append(r) or httpx.Response(204))
        ),
    )

    notifier.notify(an_event())
    notifier._submit(lambda: None).result(timeout=5)

    assert len(delivered) == 1


def a_settings(env: dict[str, str], monkeypatch: pytest.MonkeyPatch, **extra: str) -> Settings:
    for name, value in {**env, **extra}.items():
        monkeypatch.setenv(name, value)
    return Settings()  # type: ignore[call-arg]


def test_a_blank_url_wires_the_null_notifier(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = a_settings(env, monkeypatch, NOTIFY_WEBHOOK_URL="")

    notifier = build_notifier(settings)

    assert isinstance(notifier, NullNotifier)
    assert isinstance(notifier, Notifier)
    notifier.notify(an_event())


def test_a_url_wires_one_shared_webhook_notifier(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = a_settings(
        env,
        monkeypatch,
        NOTIFY_WEBHOOK_URL=HOOK,
        NOTIFY_WEBHOOK_SECRET="s3cret",
        NOTIFY_WEBHOOK_FORMAT="slack",
    )

    first, second = build_notifier(settings), build_notifier(settings)

    assert isinstance(first, WebhookNotifier)
    assert first is second
    assert settings.notify_webhook_secret == SecretStr("s3cret")
