"""`seed_harnesses` and `list_harnesses` (SPEC CAP-3, AD-10)."""

from __future__ import annotations

from orchestrator.application.use_cases.harnesses import (
    HarnessPorts,
    list_harnesses,
    seed_harnesses,
)
from orchestrator.domain.entities.harness import Harness
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.harnesses import FakeHarnessRepository

PINS = {"claude": "2.1.258", "codex": "0.152.1", "local": "1.18.26"}


def ports(harnesses: FakeHarnessRepository) -> HarnessPorts:
    uow = FakeUnitOfWork()
    uow.__enter__()
    return HarnessPorts(uow=uow, harnesses=harnesses)


def test_seeding_an_empty_store_inserts_every_name_disabled() -> None:
    harnesses = FakeHarnessRepository()

    seeded = seed_harnesses(ports(harnesses), PINS)

    assert {harness.name: harness.enabled for harness in seeded} == {
        "claude": False,
        "codex": False,
        "local": False,
    }
    assert {harness.name: harness.version_pin for harness in seeded} == PINS


def test_seeding_a_stored_name_only_refreshes_version_pin() -> None:
    harnesses = FakeHarnessRepository(
        [
            Harness(
                name="claude",
                enabled=True,
                failing_check="timeout",
                version_pin="2.1.100",
            )
        ]
    )

    seed_harnesses(ports(harnesses), {"claude": "2.1.258"})

    stored = harnesses.get("claude")
    assert stored is not None
    assert stored.enabled is True
    assert stored.failing_check == "timeout"
    assert stored.version_pin == "2.1.258"


def test_seeding_is_idempotent() -> None:
    harnesses = FakeHarnessRepository()
    seed_harnesses(ports(harnesses), PINS)

    seed_harnesses(ports(harnesses), PINS)

    assert {harness.name for harness in harnesses.list()} == set(PINS)


def test_list_harnesses_answers_every_stored_row() -> None:
    harnesses = FakeHarnessRepository()
    seed_harnesses(ports(harnesses), PINS)

    assert {harness.name for harness in list_harnesses(ports(harnesses))} == set(PINS)


def test_list_harnesses_is_empty_before_any_seed() -> None:
    assert list_harnesses(ports(FakeHarnessRepository())) == []
