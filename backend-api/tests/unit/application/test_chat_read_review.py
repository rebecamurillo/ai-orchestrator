"""The read pass after the 4-3 review (2026-11-03): an exception that cannot be stored is
still logged once, a gone thread closes through 4-1's `close_thread`, a rate limit stores its
stable text, and only a thread this fire closed has its error cleared."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from structlog.testing import capture_logs

from orchestrator.application.jobs import chat_read
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.ports.chat import ChatError, ChatRateLimited, ChatThreadGone, ThreadRef
from orchestrator.domain.values import Signal
from tests.unit.fakes.chat_world import World, a_reply, a_row

BUILD = "epics[1].stories[0].build"
READ_FAILED = "chat read failed"


class Stop:
    def __init__(self) -> None:
        self.world = World()
        self.world.add_channel()
        self.run = self.world.add_run()
        self.world.add_rows(a_row(self.run.id, 1, BUILD))
        self.thread = self.world.add_thread(self.run)
        assert self.thread.ref is not None
        self.ref = ThreadRef(id=self.thread.ref)

    def poll(self) -> list[dict[str, Any]]:
        with capture_logs() as logs:
            self.world.poll()
        return [line for line in logs if line["event"] == READ_FAILED]

    def stored(self) -> ChatThread:
        return self.world.threads.threads[self.thread.id]


def test_an_engine_failure_after_the_answer_committed_is_still_logged_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = Stop()
    stop.world.chat.script_replies(stop.ref, a_reply(1, body="SECRET text"))

    def down(run_id: UUID, signal: Signal) -> None:
        raise RuntimeError("engine unreachable: SECRET")

    monkeypatch.setattr(stop.world.engine, "signal", down)

    logs = stop.poll()

    assert stop.stored().state == "closed"
    assert stop.stored().error is None
    assert [r.event for r in stop.world.records.records.values()] == ["answer"]
    (line,) = logs
    assert line["error"] == "internal: RuntimeError"
    assert (line["run_id"], line["thread_id"]) == (str(stop.run.id), str(stop.thread.id))
    assert "SECRET" not in str(logs)


def test_a_gone_thread_is_closed_through_close_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    stop = Stop()
    stop.world.chat.read_errors[stop.ref.id] = ChatThreadGone("404 gone")
    calls: list[tuple[str | None, str | None]] = []
    real = chat_read.close_thread

    def spy(ports: Any, thread: ChatThread, cursor: str | None = None, **kw: Any) -> None:
        calls.append((cursor, kw.get("error")))
        real(ports, thread, cursor, **kw)

    monkeypatch.setattr(chat_read, "close_thread", spy)

    stop.poll()

    assert calls == [(None, "404 gone")]
    assert (stop.stored().state, stop.stored().error) == ("closed", "404 gone")


def test_a_rate_limit_stores_its_stable_text_so_a_new_wait_is_no_new_write() -> None:
    stop = Stop()
    chat = stop.world.chat
    chat.read_errors[stop.ref.id] = ChatRateLimited("x: 429, Retry-After 30 s", stable="x: 429")
    first = stop.poll()
    chat.read_errors[stop.ref.id] = ChatRateLimited("x: 429, Retry-After 12 s", stable="x: 429")

    second = stop.poll()

    assert stop.stored().error == "x: 429"
    assert [line["error"] for line in first] == ["x: 429"]
    assert second == []


def test_a_rate_limit_without_a_stable_text_stores_its_detail() -> None:
    stop = Stop()
    stop.world.chat.read_errors[stop.ref.id] = ChatRateLimited("429 slow down")

    stop.poll()

    assert stop.stored().error == "429 slow down"


def test_an_answered_batch_does_not_clear_a_thread_that_is_not_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = Stop()
    stop.world.chat.read_errors[stop.ref.id] = ChatError("502 bad gateway")
    stop.poll()
    del stop.world.chat.read_errors[stop.ref.id]
    stop.world.chat.script_replies(stop.ref, a_reply(1))

    def failed_meanwhile(ports: Any, read: ChatThread, replies: Any) -> list[tuple[str, str]]:
        stop.world.threads.threads[read.id] = replace(stop.stored(), state="failed")
        return [("r1", "answered")]

    monkeypatch.setattr(chat_read, "apply_reply_batch", failed_meanwhile)

    stop.poll()

    assert (stop.stored().state, stop.stored().error) == ("failed", "502 bad gateway")
