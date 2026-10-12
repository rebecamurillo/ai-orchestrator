"""In-memory `Notifier` — the one fake for that port (AD-18). Reuse it; do not write another."""

from __future__ import annotations

from orchestrator.domain.ports.notifier import RunNotification


class FakeNotifier:
    """Keeps every event it is handed, in order."""

    def __init__(self) -> None:
        self.events: list[RunNotification] = []

    def notify(self, event: RunNotification) -> None:
        self.events.append(event)
