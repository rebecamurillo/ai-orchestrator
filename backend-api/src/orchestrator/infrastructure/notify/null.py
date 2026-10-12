"""`NullNotifier` — the off path behind the `Notifier` port when no webhook URL is set."""

from __future__ import annotations

from orchestrator.domain.ports.notifier import RunNotification


class NullNotifier:
    """Drops every event."""

    def notify(self, event: RunNotification) -> None:
        return None
