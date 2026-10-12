"""Posts a Run notification to a webhook. The only module that sends one over HTTP."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
import structlog

from orchestrator.domain.ports.notifier import RunNotification
from orchestrator.infrastructure.notify.format import SIGNATURE_HEADER, render, sign
from orchestrator.infrastructure.settings import NotifyFormat

log = structlog.get_logger(__name__)

#: A transition happens inside a unit of work, so delivery is handed to a worker and bounded.
TIMEOUT_SECONDS = 5.0

Submit = Callable[..., Any]


class WebhookNotifier:
    """Delivers each event once, off the caller's thread; a failure is logged and dropped."""

    def __init__(  # noqa: PLR0913 — one keyword per setting this adapter reads
        self,
        *,
        url: str,
        secret: str,
        fmt: NotifyFormat,
        base_url: str,
        client: httpx.Client | None = None,
        submit: Submit | None = None,
    ) -> None:
        self._url = url.strip()
        self._secret = secret
        self._format = fmt
        self._base_url = base_url
        self._client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
        self._submit = submit or ThreadPoolExecutor(max_workers=1).submit

    def notify(self, event: RunNotification) -> None:
        self._submit(self.deliver, event)

    def deliver(self, event: RunNotification) -> None:
        """Post `event`; log and return on any failure, including an unsuccessful status."""
        headers = {"Content-Type": "application/json"}
        body = render(event, self._format, self._base_url)
        if self._secret:
            headers[SIGNATURE_HEADER] = sign(self._secret, body)
        try:
            self._client.post(self._url, content=body, headers=headers).raise_for_status()
        except httpx.HTTPError as error:
            log.warning(
                "notify_failed",
                run_id=str(event.run_id),
                status=event.status,
                error=type(error).__name__,
            )
