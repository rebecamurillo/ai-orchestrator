"""`sync_pins` resets `last_readiness_at` on a pin change (story 2-4).

New behaviour: when a harness had a prior readiness run the operator must re-run it after a
version-pin change, so `last_readiness_at` is cleared to `None` together with the disable.
"""

from __future__ import annotations

from datetime import UTC, datetime

from orchestrator.application.use_cases.harness_readiness_seed import sync_pins
from orchestrator.application.use_cases.harnesses import HarnessPorts
from orchestrator.domain.entities.harness import Harness
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.harnesses import FakeHarnessRepository


def harness_ports(harnesses: list[Harness]) -> tuple[HarnessPorts, FakeUnitOfWork]:
    uow = FakeUnitOfWork()
    ports = HarnessPorts(uow=uow, harnesses=FakeHarnessRepository(harnesses))
    return ports, uow


def test_sync_pins_resets_last_readiness_at_on_pin_change() -> None:
    """A prior `last_readiness_at` is stale after a pin change — clear it so the badge
    does not show a timestamp that predates the new version."""
    prior_run = datetime(2026, 3, 4, tzinfo=UTC)
    ports, uow = harness_ports(
        [Harness(name="claude", enabled=True, version_pin="2.1.258", last_readiness_at=prior_run)]
    )

    with uow:
        changed = sync_pins(ports, {"claude": "2.1.260"})

    assert len(changed) == 1
    stored = ports.harnesses.get("claude")
    assert stored is not None
    # last_readiness_at must be cleared — the prior timestamp is no longer meaningful
    assert stored.last_readiness_at is None
    # failing_check still records the pin transition as before
    assert stored.failing_check == "version pin changed: 2.1.258 → 2.1.260"
    assert stored.version_pin == "2.1.260"
    assert stored.enabled is False
    assert uow.committed is True
