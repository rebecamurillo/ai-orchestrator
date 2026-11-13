"""The facts sweep wired: its job entry, its registration and its ports (AC10)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from orchestrator.application.use_cases.record_attempt_facts import FactsPorts
from orchestrator.infrastructure.db.writers import open_facts_ports
from orchestrator.infrastructure.dbos.startup import schedule_facts_jobs, serving, walker_deps
from orchestrator.infrastructure.facts_jobs import FACTS_SWEEP_NAME, facts_jobs
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.git import FakeGit


class RecordingEngine:
    def __init__(self) -> None:
        self.scheduled: list[tuple[str, str]] = []

    def schedule(self, name: str, cron: str, job: Callable[[], None]) -> None:
        self.scheduled.append((name, cron))


class NoRows:
    def all(self) -> list[Any]:
        return []


class ClosingSession:
    def __init__(self) -> None:
        self.closed = False
        self.rolled_back = False

    def scalars(self, _statement: Any) -> NoRows:
        return NoRows()

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def sessions() -> Callable[[], Any]:
    def factory() -> None:  # pragma: no cover — never called: building the jobs opens none
        raise AssertionError("no session is opened while the jobs are built")

    return factory


def test_the_default_cron_is_hourly_and_the_job_is_named(env: dict[str, str]) -> None:
    assert Settings().facts_sweep_cron == "0 * * * *"
    [(name, cron, _job)] = facts_jobs(Settings(), sessions())
    assert (name, cron) == (FACTS_SWEEP_NAME, "0 * * * *")


def test_serving_registers_the_sweep_and_nothing_outside_it(env: dict[str, str]) -> None:
    engine = RecordingEngine()
    schedule_facts_jobs(Settings())
    with serving(engine):
        schedule_facts_jobs(Settings())
    assert engine.scheduled == []

    with serving(engine, sessions(), FakeGit()):
        schedule_facts_jobs(Settings())
    assert engine.scheduled == [(FACTS_SWEEP_NAME, "0 * * * *")]


def test_the_job_runs_a_sweep_in_its_own_session(env: dict[str, str]) -> None:
    session = ClosingSession()
    [(_name, _cron, job)] = facts_jobs(Settings(), lambda: session)
    job()
    assert session.closed


def test_open_facts_ports_yields_ports_and_closes_its_session() -> None:
    session = ClosingSession()
    with open_facts_ports(lambda: session, {}) as ports:  # type: ignore[arg-type, return-value]
        assert isinstance(ports, FactsPorts)
        assert not session.closed
    assert session.closed


def test_the_walker_hands_its_steps_a_facts_scope(env: dict[str, str]) -> None:
    deps = walker_deps(Settings(), sessions(), FakeGit())  # type: ignore[arg-type, return-value]
    assert deps.step_ports.facts_writes is not None
