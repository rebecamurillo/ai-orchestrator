"""`infrastructure/dbos/startup.py`: building the engine, and the guard around its launch.

Two claims, and both of them are about what does *not* happen. Building the engine opens no
connection and registers nothing, because every unit test that builds the composition root
builds one. And `launch_engine` launches only inside `serving`, which is the length of the
server's own life — so `main.run_migrations`, called directly by a unit test, reaches the
fourth start-up step and does nothing at all with it.
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.infrastructure.dbos.startup import (
    build_engine,
    launch_engine,
    serving,
    walker_deps,
)
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.git import FakeGit


class Recording:
    """Stands in for the engine `serving` is handed; records that it was launched."""

    def __init__(self) -> None:
        self.launches = 0

    def launch(self) -> None:
        self.launches += 1


def sessions() -> Any:
    def factory() -> Any:  # pragma: no cover — never called: nothing here opens a session
        raise AssertionError("no session is opened while the engine is built")

    return factory


def test_the_engine_it_builds_is_the_port(env: dict[str, str]) -> None:
    engine = build_engine(Settings(), sessions(), FakeGit())

    assert isinstance(engine, WorkflowEngine)


def test_building_the_engine_opens_nothing(env: dict[str, str]) -> None:
    """`main()` builds one before uvicorn runs, and unit tests drive `main()`."""
    build_engine(Settings(), sessions(), FakeGit())


def test_nothing_is_launched_outside_a_serving_process() -> None:
    launch_engine()


def test_the_engine_being_served_with_is_the_one_launched() -> None:
    engine = Recording()

    with serving(engine):
        launch_engine()

    assert engine.launches == 1


def test_serving_hands_back_the_engine_it_was_given() -> None:
    engine = Recording()

    with serving(engine) as served:
        assert served is engine


def test_a_process_that_stopped_serving_launches_nothing_again() -> None:
    """Otherwise one test's `main()` would leave the next one's `run_migrations` armed."""
    engine = Recording()
    with serving(engine):
        pass

    launch_engine()

    assert engine.launches == 0


def test_the_engine_is_released_even_when_serving_raises() -> None:
    engine = Recording()

    with pytest.raises(RuntimeError, match="uvicorn fell over"), serving(engine):
        raise RuntimeError("uvicorn fell over")

    launch_engine()
    assert engine.launches == 0


def test_the_walker_is_wired_to_the_settings_it_will_run_on(env: dict[str, str]) -> None:
    """The one path `HUMAN_WAIT_SECONDS` takes to the walker's `recv`, pinned end to end."""
    settings = Settings()
    git = FakeGit()

    deps = walker_deps(settings, sessions(), git)

    assert deps.human_wait_seconds == settings.human_wait_seconds
    assert deps.step_ports.git is git
    assert deps.step_ports.work_dir == str(settings.work_dir)
    assert deps.step_ports.clock is not None


def test_the_walkers_ports_open_a_session_only_when_a_step_asks(env: dict[str, str]) -> None:
    """`sessions()` refuses to be called; building the deps must not call it."""
    walker_deps(Settings(), sessions(), FakeGit())
