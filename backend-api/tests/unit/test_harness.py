"""The `Harness` entity and the `HarnessRepository` port (SPEC CAP-3, AD-10)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.domain.entities.harness import Harness
from orchestrator.domain.ports.harnesses import HarnessRepository
from tests.unit.fakes.harnesses import FakeHarnessRepository


def test_a_harness_defaults_to_disabled_and_no_readiness() -> None:
    harness = Harness(name="claude", version_pin="2.1.258")

    assert harness.enabled is False
    assert harness.last_readiness_at is None
    assert harness.failing_check is None


def test_a_harness_is_frozen() -> None:
    harness = Harness(name="claude", version_pin="2.1.258")

    with pytest.raises(ValidationError):
        harness.enabled = True  # type: ignore[misc]


def test_the_fake_satisfies_the_port() -> None:
    fake = FakeHarnessRepository()

    assert isinstance(fake, HarnessRepository)


def test_the_fake_stores_by_name_and_refuses_a_duplicate() -> None:
    fake = FakeHarnessRepository()
    fake.add(Harness(name="claude", version_pin="2.1.258"))

    with pytest.raises(ValueError, match="already stored"):
        fake.add(Harness(name="claude", version_pin="2.1.258"))


def test_get_answers_none_for_an_unstored_name() -> None:
    fake = FakeHarnessRepository()

    assert fake.get("claude") is None


def test_update_replaces_the_stored_harness() -> None:
    fake = FakeHarnessRepository([Harness(name="claude", version_pin="2.1.258")])

    fake.update(Harness(name="claude", enabled=True, version_pin="2.1.259"))

    stored = fake.get("claude")
    assert stored is not None
    assert stored.enabled is True
    assert stored.version_pin == "2.1.259"


def test_update_of_an_unstored_name_raises() -> None:
    fake = FakeHarnessRepository()

    with pytest.raises(ValueError, match="no harness"):
        fake.update(Harness(name="claude", version_pin="2.1.258"))


def test_list_is_ordered_by_name() -> None:
    fake = FakeHarnessRepository(
        [
            Harness(name="local", version_pin="1.18.26"),
            Harness(name="claude", version_pin="2.1.258"),
            Harness(name="codex", version_pin="0.152.1"),
        ]
    )

    assert [harness.name for harness in fake.list()] == ["claude", "codex", "local"]
