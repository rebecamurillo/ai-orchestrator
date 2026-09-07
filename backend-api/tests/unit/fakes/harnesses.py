"""In-memory `HarnessRepository` — the one fake for that port (AD-18). Do not write another.

It holds entities, not rows, keyed by `name` the way the table's primary key is.
"""

from __future__ import annotations

from orchestrator.domain.entities.harness import Harness


class FakeHarnessRepository:
    """Stored harnesses in a dictionary, keyed by name."""

    def __init__(self, harnesses: list[Harness] | None = None) -> None:
        self.harnesses: dict[str, Harness] = {}
        for harness in harnesses or []:
            self.add(harness)

    def add(self, harness: Harness) -> None:
        if harness.name in self.harnesses:
            raise ValueError(f"a harness named {harness.name!r} is already stored")
        self.harnesses[harness.name] = harness

    def get(self, name: str) -> Harness | None:
        return self.harnesses.get(name)

    def update(self, harness: Harness) -> None:
        if harness.name not in self.harnesses:
            raise ValueError(f"no harness named {harness.name!r} is stored")
        self.harnesses[harness.name] = harness

    def list(self) -> list[Harness]:
        return sorted(self.harnesses.values(), key=lambda harness: harness.name)
