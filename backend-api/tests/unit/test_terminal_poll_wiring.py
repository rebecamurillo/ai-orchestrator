"""Wiring `terminal_poll` (6.7, SPEC CAP-7, FR-21): `infrastructure/terminal_jobs.py::
engine_jobs` and `infrastructure/dbos/startup.py::schedule_engine_jobs`.

**Why it registers apart from the other two jobs**, which is the fact this file exists to
hold: `infrastructure/jobs.py::scheduled_jobs(settings, session_factory, git)` is never
handed a `WorkflowEngine`, and `terminal_poll`'s whole output is a `signal_run` call, which
takes one (`SignalPorts`). `_SERVING` in `startup.py` is where the engine already is, so the
job that needs it is built there. `tests/unit/test_scheduled_jobs.py` (story 4-11) states
that `scheduled_jobs` is exactly `[clone_check, worktree_gc]` and that `schedule_jobs`
registers exactly those two; both statements stay true, and this file is the third job's own.

Proved the way that module proves its two: the same `_SERVING` guard, the same
`RecordingEngine`, and the same "building the closures opens no session".
"""

from __future__ import annotations

from collections.abc import Callable

from orchestrator.infrastructure.dbos.startup import (
    schedule_engine_jobs,
    schedule_jobs,
    serving,
)
from orchestrator.infrastructure.jobs import CLONE_CHECK_NAME, WORKTREE_GC_NAME
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.terminal_jobs import TERMINAL_POLL_NAME, engine_jobs
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit

#: A cron with a seconds field: `s m h dom mon dow`, six where a minute-resolution cron has
#: five.
SECONDS_CRON_FIELDS = 6


class RecordingEngine:
    """`test_scheduled_jobs.py`'s own stand-in: records every `schedule` call."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[str, str]] = []

    def schedule(self, name: str, cron: str, job: Callable[[], None]) -> None:
        self.scheduled.append((name, cron))


def sessions() -> Callable[[], None]:
    def factory() -> None:  # pragma: no cover — never called: building the jobs opens none
        raise AssertionError("no session is opened while the jobs are built")

    return factory


def test_engine_jobs_names_the_poll_and_reads_its_cron_off_settings(
    env: dict[str, str],
) -> None:
    settings = Settings()

    jobs = engine_jobs(settings, sessions(), FakeGit(), FakeWorkflowEngine())

    assert [(name, cron) for name, cron, _ in jobs] == [
        (TERMINAL_POLL_NAME, settings.terminal_poll_cron)
    ]


def test_the_polls_cron_is_a_six_field_one_because_its_period_is_seconds(
    env: dict[str, str],
) -> None:
    """AD-20: the schedule is the environment's, never a constant — and `.env.example`'s own
    value is the 30 seconds the brief asks for."""
    assert len(Settings().terminal_poll_cron.split()) == SECONDS_CRON_FIELDS
    assert Settings().terminal_poll_cron.startswith("*/30 ")


def test_building_the_job_opens_no_session(env: dict[str, str]) -> None:
    """`sessions()` refuses to be called; building the closure must not call it."""
    engine_jobs(Settings(), sessions(), FakeGit(), FakeWorkflowEngine())


def test_nothing_is_scheduled_outside_a_serving_process(env: dict[str, str]) -> None:
    schedule_engine_jobs(Settings())


def test_a_serving_call_with_no_adapters_registers_nothing(env: dict[str, str]) -> None:
    engine = RecordingEngine()

    with serving(engine):
        schedule_engine_jobs(Settings())

    assert engine.scheduled == []


def test_serving_with_the_apps_own_adapters_registers_the_poll(env: dict[str, str]) -> None:
    engine = RecordingEngine()

    with serving(engine, sessions(), FakeGit()):
        schedule_engine_jobs(Settings())

    assert [name for name, _ in engine.scheduled] == [TERMINAL_POLL_NAME]


def test_the_two_registrations_together_are_the_three_jobs(env: dict[str, str]) -> None:
    """What `main.py` does, and the whole reason the split is invisible in production: the
    sweeps and the poll are all registered, each by the function that can build it."""
    engine = RecordingEngine()

    with serving(engine, sessions(), FakeGit()):
        schedule_jobs(Settings())
        schedule_engine_jobs(Settings())

    assert [name for name, _ in engine.scheduled] == [
        CLONE_CHECK_NAME,
        WORKTREE_GC_NAME,
        TERMINAL_POLL_NAME,
    ]


def test_a_process_that_stopped_serving_schedules_nothing_again(env: dict[str, str]) -> None:
    engine = RecordingEngine()
    with serving(engine, sessions(), FakeGit()):
        pass

    schedule_engine_jobs(Settings())

    assert engine.scheduled == []
