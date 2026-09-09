"""Where the scripted `fake` harness is admitted, and where it is not (SPEC CAP-1, AR-14).

The operator's rule for this harness is that it must be reachable in test mode and reachable
*nowhere else* — not in a Template's `values`, not on New workflow, not by a Run an Operator
creates. There is no enum to enforce that with: a bound `harness` value is never checked
against a Template's declared values (`templates/inputs.py` reads them only to validate a
default), and `api/schemas/runs.py` types the field `str | None`. The gate is pre-flight's
harness line, which fails for a name with no `harness` row. So "registered under
`ORCH_TEST_MODE`, and its row seeded only there" *is* the conditional, and it is what this
module pins — including the half that matters most, which is that both are absent by default.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from orchestrator.application.use_cases.harnesses import HarnessPorts, seed_test_harness
from orchestrator.domain.entities.harness import HARNESS_NAMES, Harness
from orchestrator.infrastructure.db import seed as db_seed
from orchestrator.infrastructure.harness import build_harnesses
from orchestrator.infrastructure.harness.fake import NAME, FakeHarness
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.process import FakeProcessRunner


@contextmanager
def ports() -> Iterator[tuple[HarnessPorts, FakeHarnessRepository]]:
    """One open unit of work, the way `seed_harness_table` opens one around the seeds."""
    repository = FakeHarnessRepository()
    with FakeUnitOfWork() as uow:
        yield HarnessPorts(uow=uow, harnesses=repository), repository


# ── the registry ────────────────────────────────────────────────────────────────────────


def test_the_contracts_own_default_registers_no_fake_harness(env: dict[str, str]) -> None:
    """`.env.example` ships `ORCH_TEST_MODE=0`, which is what every unit test reads."""
    assert Settings().orch_test_mode is False
    assert NAME not in build_harnesses(Settings(), FakeProcessRunner())


def test_test_mode_registers_it_beside_the_claude_adapter(env: dict[str, str]) -> None:
    built = build_harnesses(Settings(orch_test_mode=True), FakeProcessRunner())

    assert sorted(built) == ["claude", NAME]
    assert isinstance(built[NAME], FakeHarness)


def test_it_runs_on_the_walkers_own_runner_like_every_other_adapter(
    env: dict[str, str],
) -> None:
    """AD-14: one runner, so one object can kill every group this process started."""
    runner = FakeProcessRunner()

    built = build_harnesses(Settings(orch_test_mode=True), runner)

    assert built[NAME].runner is runner  # type: ignore[union-attr]


def test_it_is_not_one_of_the_names_the_image_installs() -> None:
    """`HARNESS_NAMES` is the three real harnesses and readiness runs against those alone;
    `fake` has no version pin setting and no readiness run, so it belongs to neither table."""
    assert NAME not in HARNESS_NAMES
    assert NAME not in db_seed.HARNESS_VERSION_SETTINGS


# ── the row ─────────────────────────────────────────────────────────────────────────────


def test_the_row_is_stored_enabled_so_pre_flight_admits_the_name() -> None:
    with ports() as (harness_ports, repository):
        seeded = seed_test_harness(harness_ports, NAME, db_seed.FAKE_HARNESS_PIN)

        assert seeded == Harness(name=NAME, enabled=True, version_pin=db_seed.FAKE_HARNESS_PIN)
        assert repository.get(NAME) == seeded


def test_a_second_start_leaves_it_enabled_rather_than_disabling_it() -> None:
    """Unlike `seed_harnesses`, this one writes `enabled` — see its docstring for why."""
    with ports() as (harness_ports, repository):
        repository.add(Harness(name=NAME, enabled=False, version_pin="stale", failing_check="x"))

        seed_test_harness(harness_ports, NAME, db_seed.FAKE_HARNESS_PIN)

        stored = repository.get(NAME)
        assert stored is not None
        assert stored.enabled is True
        assert stored.version_pin == db_seed.FAKE_HARNESS_PIN
        assert not stored.failing_check


# ── the start-up seed ───────────────────────────────────────────────────────────────────


class _Recorder:
    def __init__(self) -> None:
        self.seeded: list[str] = []


@pytest.fixture
def seeding(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    """`seed_harness_table` with every adapter it opens replaced by a do-nothing double.

    The function's whole job is ordering four use cases against one unit of work; the
    database it would otherwise open is the `.env.example` placeholder, which is not there.
    """
    recorder = _Recorder()

    class FakeEngine:
        def dispose(self) -> None:
            return None

    class FakeUow:
        def __init__(self, factory: Any) -> None:
            self.session = object()

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

    def fake_seed_test(_ports: Any, name: str, pin: str) -> Harness:
        recorder.seeded.append(name)
        return Harness(name=name, enabled=True, version_pin=pin)

    monkeypatch.setattr(db_seed, "create_engine_from", lambda settings: FakeEngine())
    monkeypatch.setattr(db_seed, "create_session_factory", lambda engine: object())
    monkeypatch.setattr(db_seed, "SQLAlchemyUnitOfWork", FakeUow)
    monkeypatch.setattr(db_seed, "SQLAlchemyHarnessRepository", lambda session: None)
    monkeypatch.setattr(db_seed, "SQLAlchemyProjectRepository", lambda session: None)
    monkeypatch.setattr(db_seed, "SQLAlchemyRepositoryRepository", lambda session: None)
    monkeypatch.setattr(db_seed, "FernetCrypto", lambda key: None)
    monkeypatch.setattr(db_seed, "SubprocessGit", lambda token: None)
    monkeypatch.setattr(db_seed, "SystemClock", lambda: None)
    monkeypatch.setattr(db_seed, "sync_pins", lambda ports, pins: [])
    monkeypatch.setattr(db_seed, "seed_harnesses", lambda ports, pins: list(pins))
    monkeypatch.setattr(db_seed, "seed_test_harness", fake_seed_test)
    monkeypatch.setattr(db_seed, "seed_readiness_project", lambda ports, **kwargs: None)
    return recorder


def test_the_start_up_seed_writes_no_fake_row_without_test_mode(
    env: dict[str, str], seeding: _Recorder
) -> None:
    seeded = db_seed.seed_harness_table(Settings())

    assert seeding.seeded == []
    assert seeded == list(db_seed.HARNESS_VERSION_SETTINGS)


def test_the_start_up_seed_adds_the_fake_row_in_test_mode(
    env: dict[str, str], seeding: _Recorder
) -> None:
    seeded = db_seed.seed_harness_table(Settings(orch_test_mode=True))

    assert seeding.seeded == [NAME]
    assert seeded[-1].name == NAME  # type: ignore[union-attr]
