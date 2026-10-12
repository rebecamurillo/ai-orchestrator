"""The bytes a Run notification is posted as, and the signature that vouches for them."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC
from typing import Any

from orchestrator.domain.ports.notifier import RunNotification
from orchestrator.infrastructure.settings import NotifyFormat

SIGNATURE_HEADER = "X-Orchestrator-Signature"

#: Longest reason a one-line chat message carries; the Run page holds the rest.
SLACK_REASON_LIMIT = 300

_HEADLINES = {
    "needs_you": "needs you",
    "done": "done",
    "failed": "failed",
    "cancelled": "cancelled",
}


def run_url(base_url: str, event: RunNotification) -> str | None:
    """The Run's page on the web client, or `None` when no public base URL is configured."""
    base = base_url.strip().rstrip("/")
    return f"{base}/workflows/{event.run_id}" if base else None


def event_payload(event: RunNotification, url: str | None) -> dict[str, Any]:
    """The structured event; `url` is left out rather than sent empty."""
    payload: dict[str, Any] = {
        "run_id": str(event.run_id),
        "project": event.project,
        "repository": event.repository,
        "template": event.template,
        "status": event.status,
        "park_kind": event.park_kind,
        "reason": event.reason,
        "step_path": event.step_path,
        "attempt_id": str(event.attempt_id) if event.attempt_id is not None else None,
        "spend_usd": str(event.spend_usd),
        "occurred_at": event.occurred_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if url is not None:
        payload["url"] = url
    return payload


def slack_text(event: RunNotification, url: str | None) -> str:
    """One message: what happened, where, why, what it cost, and the link."""
    parts = [
        f"Run {_HEADLINES[event.status]}: {event.project} / {event.repository}",
        event.template,
    ]
    if event.park_kind is not None:
        parts.append(event.park_kind)
    if event.step_path is not None:
        parts.append(event.step_path)
    if event.reason:
        parts.append(event.reason[:SLACK_REASON_LIMIT])
    parts.append(f"${event.spend_usd}")
    if url is not None:
        parts.append(url)
    return " | ".join(parts)


def render(event: RunNotification, fmt: NotifyFormat, base_url: str) -> bytes:
    """The request body for `event` in the configured format."""
    url = run_url(base_url, event)
    body = {"text": slack_text(event, url)} if fmt == "slack" else event_payload(event, url)
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode()


def sign(secret: str, body: bytes) -> str:
    """`sha256=<hex>` — the HMAC-SHA256 of the exact bytes sent."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
