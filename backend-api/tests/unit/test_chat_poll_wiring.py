"""The chat job's `SignalPorts` (story 4-3, AD-8, AD-25): `terminal_jobs` wires the engine and
both mode callables as `api/providers.py::signal_effect_ports` does, so a thread answer
resumes the recorded session; and a fire that raises anything returns normally."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from structlog.testing import capture_logs

from orchestrator.application.jobs.chat_ports import ChatPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ThreadRef
from orchestrator.infrastructure import terminal_jobs
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.terminal_jobs import CHAT_POLL_NAME, engine_jobs
from tests.unit.fakes.chat_world import World, a_reply, a_row
from tests.unit.fakes.git import FakeGit

BUILD = "epics[1].stories[0].build"


class Wired:
    """A World behind the real chat job: its ports, factory, crypto and engine."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.world = World()
        self.world.add_channel()
        self.run = self.world.add_run()
        self.world.add_rows(a_row(self.run.id, 1, BUILD))
        self.thread = self.world.add_thread(self.run)
        self.opened: list[ChatPorts] = []
        monkeypatch.setattr(terminal_jobs, "open_chat_ports", self._open)
        monkeypatch.setattr(terminal_jobs, "crypto_factory", lambda settings: self.world._crypto)
        monkeypatch.setattr(terminal_jobs, "CHAT_SLOT", [self.world.factory])

    @contextmanager
    def _open(self, session_factory: Any, notifier: Any = None) -> Iterator[ChatPorts]:
        ports = self.world.chat_ports()
        self.opened.append(ports)
        yield ports

    def job(self) -> Callable[[], None]:
        jobs = engine_jobs(
            Settings(), _no_sessions, FakeGit(), self.world.engine, chat=self.world.factory
        )
        return next(job for name, _, job in jobs if name == CHAT_POLL_NAME)

    def attempt(self, harness: str) -> Attempt:
        attempt = Attempt(
            id=new_id(),
            run_id=self.run.id,
            step_run_id=new_id(),
            n=1,
            status="done",
            started_at=self.world.clock.now(),
            harness=harness,
            session_id="sess-1",
        )
        self.world.attempts.add(attempt)
        return attempt

    def answer_mode(self) -> object:
        (answer,) = [r for r in self.world.records.records.values() if r.event == "answer"]
        return answer.payload["mode"]


def _no_sessions() -> None:
    raise AssertionError("no session is opened: the chat ports are faked")


def test_an_answer_resumes_the_session_of_a_resuming_harness(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    wired = Wired(monkeypatch)
    wired.attempt("claude")
    assert wired.thread.ref is not None
    wired.world.chat.script_replies(ThreadRef(id=wired.thread.ref), a_reply(1))

    wired.job()()

    assert wired.answer_mode() == "session"
    assert [name for name, _ in wired.world.engine.calls].count("signal") == 1


def test_an_answer_restarts_when_the_harness_is_unknown(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    wired = Wired(monkeypatch)
    wired.attempt("no-such-harness")
    assert wired.thread.ref is not None
    wired.world.chat.script_replies(ThreadRef(id=wired.thread.ref), a_reply(1))

    wired.job()()

    assert wired.answer_mode() == "restart"


def test_the_latest_attempt_is_read_on_the_fires_own_writers(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    wired = Wired(monkeypatch)
    seen: list[Any] = []
    monkeypatch.setattr(terminal_jobs, "run_chat_poll", seen.append)

    wired.job()()

    (ports,) = seen
    (opened,) = wired.opened
    assert ports.signal.writers is opened.writers
    assert ports.signal.engine is wired.world.engine
    ports.signal.latest_attempt_for_run(wired.run.id)
    assert ("latest_for_run", wired.run.id) in wired.world.attempts.calls


def test_a_fire_that_raises_anything_returns_normally(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    wired = Wired(monkeypatch)

    def refused(session_factory: Any, notifier: Any = None) -> Iterator[ChatPorts]:
        raise RuntimeError("database unreachable: SECRET")

    monkeypatch.setattr(terminal_jobs, "open_chat_ports", refused)

    with capture_logs() as logs:
        wired.job()()

    assert logs == [
        {"event": "chat poll failed", "log_level": "warning", "error_class": "RuntimeError"}
    ]
