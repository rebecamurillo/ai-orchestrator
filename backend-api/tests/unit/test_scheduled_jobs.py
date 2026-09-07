"""Wiring the two scheduled jobs (SPEC CAP-11): `infrastructure/jobs.py::scheduled_jobs`,
and `infrastructure/dbos/startup.py::schedule_jobs` reaching the engine `serving` names.

`test_dbos_startup.py` is frozen and its own `serving(engine)` calls — one positional
argument — must keep working unchanged; this module is the new behaviour `serving`'s two
extra, optional parameters add, proven the way that module proves `launch_engine`: guarded
by the same `_SERVING` list, empty in every process that never entered `serving`.
"""

from __future__ import annotations

from collections.abc import Callable

from orchestrator.infrastructure.dbos.startup import schedule_jobs, serving
from orchestrator.infrastructure.jobs import CLONE_CHECK_NAME, WORKTREE_GC_NAME, scheduled_jobs
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.git import FakeGit


class RecordingEngine:
    """Stands in for the engine `serving` is handed; records every `schedule` call."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[str, str]] = []

    def schedule(self, name: str, cron: str, job: Callable[[], None]) -> None:
        self.scheduled.append((name, cron))


def sessions() -> Callable[[], None]:
    def factory() -> None:  # pragma: no cover — never called: building the jobs opens none
        raise AssertionError("no session is opened while the jobs are built")

    return factory


def test_scheduled_jobs_names_both_and_reads_their_crons_off_settings(
    env: dict[str, str],
) -> None:
    settings = Settings()

    jobs = scheduled_jobs(settings, sessions(), FakeGit())

    names_and_crons = [(name, cron) for name, cron, _ in jobs]
    assert names_and_crons == [
        (CLONE_CHECK_NAME, settings.clone_check_cron),
        (WORKTREE_GC_NAME, settings.worktree_gc_cron),
    ]


def test_building_the_jobs_opens_no_session(env: dict[str, str]) -> None:
    """`sessions()` refuses to be called; building the closures must not call it."""
    scheduled_jobs(Settings(), sessions(), FakeGit())


def test_nothing_is_scheduled_outside_a_serving_process(env: dict[str, str]) -> None:
    schedule_jobs(Settings())


def test_a_serving_call_with_no_adapters_registers_nothing(env: dict[str, str]) -> None:
    """`test_dbos_startup.py`'s own `serving(engine)` calls: no session factory, no git,
    nothing scheduled — the same shape a process that never named them keeps."""
    engine = RecordingEngine()

    with serving(engine):
        schedule_jobs(Settings())

    assert engine.scheduled == []


def test_serving_with_the_apps_own_adapters_registers_both_jobs(env: dict[str, str]) -> None:
    engine = RecordingEngine()

    with serving(engine, sessions(), FakeGit()):
        schedule_jobs(Settings())

    assert [name for name, _ in engine.scheduled] == [CLONE_CHECK_NAME, WORKTREE_GC_NAME]


def test_a_process_that_stopped_serving_schedules_nothing_again(env: dict[str, str]) -> None:
    engine = RecordingEngine()
    with serving(engine, sessions(), FakeGit()):
        pass

    schedule_jobs(Settings())

    assert engine.scheduled == []
