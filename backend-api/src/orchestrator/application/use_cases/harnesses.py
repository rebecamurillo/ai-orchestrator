"""Reading and seeding harnesses (SPEC CAP-3, AD-10).

- **`list_harnesses`** answers `GET /harnesses` — a straight read.
- **`seed_harnesses`** is `main.py`'s start-up step (mirrors `templates.py::seed_shipped`): every
  name in `pins` gets a stored row. A name already stored keeps its `enabled`,
  `last_readiness_at` and `failing_check` — only Epic 5's readiness use case writes those — and
  only its `version_pin` is refreshed, so a redeployed image with a new pinned version is
  reflected without disturbing what readiness already found. A name not yet stored is inserted
  disabled, with no readiness recorded.
- **`seed_test_harness`** is SPEC CAP-1's own row: the scripted `fake` harness, stored
  *enabled*. It is the one harness readiness never proves, because there is nothing to
  prove — it runs no model, spends nothing, and exports no trace, so every line AD-10's
  readiness run checks would be vacuous for it. Enabling it by fiat is therefore the honest
  record, and it is written on every start under `ORCH_TEST_MODE` so an instance that has
  test mode on always has a usable row, whatever a previous start left. `main.py` calls it
  only in that mode, so an Operator's instance has no such row at all and pre-flight refuses
  the name — which is what keeps `fake` off every screen without touching a Template.
- **`seed_disabled_harness`** (story 9-4) marks a named harness disabled with a specific
  `failing_check` reason. Called from `seed_harness_table` after `seed_harnesses` when the
  Gateway is off, so `local`'s row reflects the permanent reason it cannot be used rather
  than "no readiness run" (which implies the situation is recoverable by running readiness).
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


def seed_test_harness(ports: HarnessPorts, name: str, pin: str) -> Harness:
    """Store `name` enabled, inserting or replacing (SPEC CAP-1). Test mode only.

    Unlike `seed_harnesses` this *does* write `enabled`, and deliberately: readiness is the
    authority for a harness whose readiness can be run, and this is the one whose cannot.
    `failing_check` and `last_readiness_at` are left at their defaults for the same reason —
    there is no readiness run to report, and stating one would be a fact this never observed.
    """
    harness = Harness(name=name, enabled=True, version_pin=pin)
    if ports.harnesses.get(name) is None:
        ports.harnesses.add(harness)
    else:
        ports.harnesses.update(harness)
    ports.uow.commit()
    return harness


def seed_disabled_harness(ports: HarnessPorts, name: str, reason: str) -> Harness:
    """Store `name` disabled with `failing_check=reason` (story 9-4, gateway-off startup).

    Written *after* `seed_harnesses` so it always overwrites an existing row and never
    relies on insert. If the row is somehow absent (defensive), inserts with
    `version_pin="unknown"` so the row is well-formed while the service that would supply a
    real pin is off.

    The `reason` string surfaces in `harness_line`'s `disabled: {reason}` output so an
    Operator can see immediately why the harness is unavailable, rather than the generic
    "no readiness run" that implies the situation is recoverable by running readiness.
    """
    existing = ports.harnesses.get(name)
    if existing is None:
        harness = Harness(name=name, version_pin="unknown", enabled=False, failing_check=reason)
        ports.harnesses.add(harness)
    else:
        harness = existing.model_copy(update={"enabled": False, "failing_check": reason})
        ports.harnesses.update(harness)
    ports.uow.commit()
    return harness
