"""The `Notifier` adapter, behind one package (AD-2).

`build_notifier(settings)` is the single decision point: a `WebhookNotifier` when
`settings.notify_enabled`, otherwise a `NullNotifier`. `httpx` is imported only in
`webhook.py`.
"""

from __future__ import annotations

from functools import cache

from orchestrator.domain.ports.notifier import Notifier
from orchestrator.infrastructure.notify.null import NullNotifier
from orchestrator.infrastructure.notify.webhook import WebhookNotifier
from orchestrator.infrastructure.settings import NotifyFormat, Settings


def build_notifier(settings: Settings) -> Notifier:
    """The webhook adapter when `NOTIFY_WEBHOOK_URL` is set, else the null one.

    One adapter per distinct configuration, because every request-scoped port set asks for
    it and each adapter owns an HTTP client and a delivery worker.
    """
    if not settings.notify_enabled:
        return NullNotifier()
    return _webhook(
        settings.notify_webhook_url,
        settings.notify_webhook_secret.get_secret_value(),
        settings.notify_webhook_format,
        settings.public_base_url,
    )


@cache
def _webhook(url: str, secret: str, fmt: NotifyFormat, base_url: str) -> WebhookNotifier:
    return WebhookNotifier(url=url, secret=secret, fmt=fmt, base_url=base_url)


__all__ = ["NullNotifier", "WebhookNotifier", "build_notifier"]
