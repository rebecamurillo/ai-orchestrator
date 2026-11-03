"""Rate limits within one fire (story 4-2 review, lead ruling 2026-11-03): once any pass for a
Project hits `ChatRateLimited`, no later pass for that Project calls the platform in that
fire; a closing-notice `ChatError` skips the watch. The pass order stays as it is."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from orchestrator.application.jobs import chat_poll
from orchestrator.application.jobs.chat_close import post_close_notices
from orchestrator.application.jobs.chat_ports import RateLimitWatch
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.ports.chat import ChatError, ChatRateLimited, ThreadRef
from tests.unit.fakes.chat import FakeChatChannel
from tests.unit.fakes.chat_world import ALICE, HOURS, World, a_reply


class Fire:
    """A Project with an open thread at a waiting stop, a closed thread owing its notice,
    and a closed, noticed thread with a late allowed mention."""

    def __init__(self) -> None:
        self.world = World()
        self.channel = self.world.add_channel()
        self.waiting = self.world.add_thread(self.world.add_run())
        self.due = self.world.add_thread(
            self.world.add_run(status="running"),
            state="closed",
            closed_at=self.world.clock.now(),
            close_notice="due",
        )
        self.watched = self.world.add_thread(
            self.world.add_run(status="running"),
            state="closed",
            cursor="c0",
            closed_at=self.world.clock.now(),
            close_notice="posted",
        )
        self.world.chat.script_replies(self.ref(self.watched), a_reply(0), a_reply(1))

    def ref(self, thread: ChatThread) -> ThreadRef:
        assert thread.ref is not None
        return ThreadRef(id=thread.ref)

    def stored(self, thread: ChatThread) -> ChatThread:
        return self.world.threads.threads[thread.id]

    def watch_read(self) -> bool:
        return any(ref == self.ref(self.watched) for ref, _ in self.world.chat.reads)


def test_a_rate_limited_read_skips_the_closing_notices_and_the_watch() -> None:
    fire = Fire()
    fire.world.chat.read_errors[fire.ref(fire.waiting).id] = ChatRateLimited("429 wait 3s", "429")

    fire.world.poll()

    assert fire.stored(fire.due).close_notice == "due"
    assert fire.world.chat.replies == []
    assert not fire.watch_read()


def test_a_read_failure_that_is_not_a_rate_limit_still_posts_the_closing_notices() -> None:
    fire = Fire()
    fire.world.chat.read_errors[fire.ref(fire.waiting).id] = ChatError("502")

    fire.world.poll()

    assert fire.stored(fire.due).close_notice == "posted"
    assert not fire.watch_read()


def test_a_rate_limited_reminder_skips_every_later_pass() -> None:
    fire = Fire()
    fire.world.clock.advance(HOURS * 3600)
    fire.world.chat.fail_next(ChatRateLimited("429 wait 3s", "429"))

    fire.world.poll()

    assert fire.world.chat.reads == []
    assert fire.world.chat.replies == []
    assert fire.stored(fire.due).close_notice == "due"
    assert fire.stored(fire.waiting).last_reminded_at is not None


def test_a_rate_limited_post_skips_every_later_pass() -> None:
    fire = Fire()
    fire.world.add_run()
    fire.world.clock.advance(HOURS * 3600)
    fire.world.chat.fail_next(ChatRateLimited("429 wait 3s", "429"))

    fire.world.poll()

    assert fire.world.chat.posts == []
    assert fire.world.chat.reads == []
    assert fire.world.chat.replies == []
    assert fire.stored(fire.waiting).last_reminded_at is None
    assert fire.stored(fire.due).close_notice == "due"


def test_a_failed_closing_notice_skips_the_watch() -> None:
    fire = Fire()
    sends: list[bool] = []

    def fail_first() -> None:
        sends.append(True)
        if len(sends) == 1:
            fire.world.chat.fail_next(ChatError("500"))

    fire.world.chat.on_send = fail_first

    fire.world.poll()

    assert fire.stored(fire.due).close_notice == "failed"
    assert not fire.watch_read()
    assert fire.stored(fire.watched).mention_notice is None


def test_a_clean_fire_still_watches() -> None:
    fire = Fire()

    fire.world.poll()

    assert fire.stored(fire.due).close_notice == "posted"
    assert fire.stored(fire.watched).mention_notice == "posted"


def test_the_closing_notice_pass_reports_a_chat_error() -> None:
    fire = Fire()
    ports = fire.world.ports()

    assert post_close_notices(ports, fire.channel, fire.world.chat) is False

    fire.world.threads.threads[fire.due.id] = fire.due
    fire.world.chat.fail_next(ChatError("500"))
    assert post_close_notices(ports, fire.channel, fire.world.chat) is True


def test_the_closing_notice_pass_reports_no_error_when_its_list_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fire = Fire()

    def failing(_: Any) -> list[ChatThread]:
        raise RuntimeError("down")

    monkeypatch.setattr(fire.world.threads, "list_notices_due", failing)

    assert post_close_notices(fire.world.ports(), fire.channel, fire.world.chat) is False


# ── the watch on the channel ───────────────────────────────────────────────────────────


def test_the_watch_delegates_every_call_and_records_a_rate_limit() -> None:
    chat = FakeChatChannel()
    watch = RateLimitWatch(chat)
    root = watch.post("hello", (ALICE,), "\nRun: x")
    watch.reply(root, "again")
    chat.script_replies(root, a_reply(1))

    assert watch.replies_since(root, None) == [a_reply(1)]
    assert watch.follows("c1", None) is True
    assert watch.rendered_length("ab", (), "c") == chat.rendered_length("ab", (), "c")
    assert watch.probe() == chat.probe_handle
    assert chat.posts == [("hello\nRun: x", (ALICE,))]
    assert chat.replies == [(root, "again")]
    assert watch.rate_limited is False

    chat.fail_next(ChatError("500"))
    with pytest.raises(ChatError):
        watch.reply(root, "x")
    assert watch.rate_limited is False


@pytest.mark.parametrize("call", ["post", "reply", "replies_since", "probe"])
def test_a_rate_limit_on_any_call_is_recorded_and_raised(call: str) -> None:
    chat = FakeChatChannel()
    watch = RateLimitWatch(chat)
    root = ThreadRef(id="t")
    chat.script_replies(root, a_reply(1))
    chat.fail_next(ChatRateLimited("429 wait 1s", "429"))
    calls: dict[str, Any] = {
        "post": lambda: watch.post("x", ()),
        "reply": lambda: watch.reply(root, "x"),
        "replies_since": lambda: watch.replies_since(root, None),
        "probe": watch.probe,
    }

    with pytest.raises(ChatRateLimited):
        calls[call]()

    assert watch.rate_limited is True


def test_the_poll_wraps_the_opened_channel_once_per_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = World()
    world.add_channel()
    seen: list[Any] = []

    def record(_: Any, channel: Any, chat: Any, *__: Any) -> bool:
        seen.append(chat)
        return False

    for name in ("remind_threads", "post_notices", "read_replies", "post_close_notices"):
        monkeypatch.setattr(chat_poll, name, record)
    monkeypatch.setattr(chat_poll, "watch_threads", record)

    world.clock.advance(int(timedelta(minutes=1).total_seconds()))
    world.poll()

    assert len(seen) == len(("remind", "notice", "read", "closing notice", "watch"))
    assert all(isinstance(chat, RateLimitWatch) for chat in seen)
    assert len({id(chat) for chat in seen}) == 1
