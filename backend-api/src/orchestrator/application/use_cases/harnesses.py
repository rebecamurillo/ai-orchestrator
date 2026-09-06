"""Reading and seeding harnesses (SPEC CAP-3, AD-10).

- **`list_harnesses`** answers `GET /harnesses` — a straight read.
- **`seed_harnesses`** is `main.py`'s start-up step (mirrors `templates.py::seed_shipped`): every
  name in `pins` gets a stored row. A name already stored keeps its `enabled`,
  `last_readiness_at` and `failing_check` — only Epic 5's readiness use case writes those — and
  only its `version_pin` is refreshed, so a redeployed image with a new pinned version is
  reflected without disturbing what readiness already found. A name not yet stored is inserted
  disabled, with no readiness recorded.
"""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.entities.harness import Harness
from orchestrator.domain.ports.harnesses import HarnessRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork


@dataclass(frozen=True)
class HarnessPorts:
    """Everything these use cases reach the outside world through."""

    uow: UnitOfWork
    harnesses: HarnessRepository


def list_harnesses(ports: HarnessPorts) -> list[Harness]:
    """Every stored harness, ordered by name."""
    return ports.harnesses.list()


def seed_harnesses(ports: HarnessPorts, pins: dict[str, str]) -> list[Harness]:
    """Idempotent upsert of `name` -> `version_pin`; `enabled` is never touched here."""
    seeded = [_seed_one(ports.harnesses, name, pin) for name, pin in pins.items()]
    ports.uow.commit()
    return seeded


def _seed_one(harnesses: HarnessRepository, name: str, pin: str) -> Harness:
    stored = harnesses.get(name)
    if stored is None:
        harness = Harness(name=name, enabled=False, version_pin=pin)
        harnesses.add(harness)
        return harness
    updated = stored.model_copy(update={"version_pin": pin})
    harnesses.update(updated)
    return updated
