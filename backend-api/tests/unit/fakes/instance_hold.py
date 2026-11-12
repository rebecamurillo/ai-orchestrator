"""In-memory `InstanceHoldRepository` — the one fake for that port (AD-18). Do not write another.

`.calls` records each port call by name, so a test can say which lock a use case took.
"""

from __future__ import annotations

from orchestrator.domain.entities.instance_hold import InstanceHold


class FakeInstanceHoldRepository:
    def __init__(self, hold: InstanceHold | None = None) -> None:
        self.hold = hold
        self.calls: list[str] = []

    def get(self) -> InstanceHold | None:
        self.calls.append("get")
        return self.hold

    def get_shared(self) -> InstanceHold | None:
        self.calls.append("get_shared")
        return self.hold

    def get_for_update(self) -> InstanceHold | None:
        self.calls.append("get_for_update")
        return self.hold

    def put(self, hold: InstanceHold) -> None:
        self.calls.append("put")
        self.hold = hold

    def delete_all(self) -> None:
        self.calls.append("delete_all")
        self.hold = None
