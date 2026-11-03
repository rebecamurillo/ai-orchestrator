"""`jobs/chat_watch.py::watch_threads` (story 4-2, CAP-12, AD-25): for 24 h after it
closes, a closed thread whose closing notice was posted is read for its first allowed reply
mentioning the bot, which gets one notice pointing to the Run page."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from structlog.testing import capture_logs

from orchestrator.application.jobs.chat_watch import watch_threads
from orchestrator.application.rules.chat_close import WATCH_HOURS, WATCH_READS_PER_FIRE
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.ports.chat import ChatError, ThreadRef
from tests.unit.fakes.chat_world import BASE_URL, BOB, World, a_reply

CLOSED = "This thread is closed. Act on the Run page"


class Watched:
    """A Project on its channel and one closed, noticed thread of a Run that ran on."""

    def __init__(self) -> None:
        self.world = World()
        self.channel = self.world.add_channel()
        self.thread = self.add()

    def add(self, **fields: Any) -> ChatThread:
        run = self.world.add_run(status="running")
        values: dict[str, Any] = {
            "state": "closed",
            "cursor": "c0",
            "closed_at": self.world.clock.now(),
            "close_notice": "posted",
        }
        values.update(fields)
        thread = self.world.add_thread(run, **values)
        self.world.chat.script_replies(self.ref(thread), a_reply(0, author_id="bot"))
        return thread

    def ref(self, thread: ChatThread) -> ThreadRef:
        assert thread.ref is not None
        return ThreadRef(id=thread.ref)

    def script(self, *replies: Any, thread: ChatThread | None = None) -> None:
        self.world.chat.script_replies(self.ref(thread or self.thread), *replies)

    def stored(self, thread: ChatThread | None = None) -> ChatThread:
        return self.world.threads.threads[(thread or self.thread).id]

    def watch(self) -> list[dict[str, Any]]:
        with capture_logs() as logs:
            watch_threads(self.world.ports(), self.channel, self.world.chat)
        return logs

    def poll(self) -> list[dict[str, Any]]:
        with capture_logs() as logs:
            self.world.poll()
        return logs

    def replies(self) -> list[str]:
        return [text for _, text in self.world.chat.replies]


def lines(logs: list[dict[str, Any]], event: str) -> list[dict[str, Any]]:
    return [line for line in logs if line["event"] == event]


def test_a_late_allowed_mention_gets_one_notice_pointing_to_the_run_page() -> None:
    watched = Watched()
    watched.script(a_reply(1, body="do X"))

    watched.poll()

    stored = watched.stored()
    url = f"{BASE_URL}/workflows/{stored.run_id}"
    assert watched.replies() == [f"{CLOSED}: {url}"]
    assert watched.world.chat.reply_mentions == [()]
    assert (stored.mention_notice, stored.mention_cursor) == ("posted", "c1")
    assert stored.mention_notice_at == watched.world.clock.now()
    assert watched.world.chat.reads == [(watched.ref(watched.thread), "c0")]


def test_without_a_base_url_the_notice_has_no_link() -> None:
    watched = Watched()
    watched.world.public_base_url = ""
    watched.script(a_reply(1))

    watched.watch()

    assert watched.replies() == [f"{CLOSED}."]


def test_two_mentions_in_one_read_and_one_next_fire_get_one_notice() -> None:
    watched = Watched()
    watched.script(a_reply(1), a_reply(2, author_id=BOB.id))
    watched.poll()
    watched.script(a_reply(3))

    watched.poll()

    assert len(watched.replies()) == 1
    assert watched.stored().mention_cursor == "c1"


def test_no_notice_after_a_restart() -> None:
    watched = Watched()
    watched.script(a_reply(1))
    watched.poll()
    watched.world.started_at = watched.world.clock.now()
    watched.world.clock.advance(60)
    watched.script(a_reply(2))

    watched.poll()

    assert len(watched.replies()) == 1


@pytest.mark.parametrize(
    "reply",
    [a_reply(1, author_id="outsider"), a_reply(1, mentions_bot=False, text="thanks")],
)
def test_an_outsider_or_an_unmentioning_reply_is_not_counted(reply: Any) -> None:
    watched = Watched()
    watched.script(reply)

    watched.watch()
    watched.watch()

    assert watched.replies() == []
    stored = watched.stored()
    assert (stored.mention_notice, stored.mention_cursor) == (None, "c1")
    assert watched.world.chat.reads[-1] == (watched.ref(watched.thread), "c1")


def test_an_empty_read_writes_nothing() -> None:
    watched = Watched()

    watched.watch()

    assert ("update", watched.thread.id) not in watched.world.threads.calls


def test_a_thread_closed_too_long_ago_or_before_the_migration_is_not_read() -> None:
    watched = Watched()
    old = watched.add(closed_at=watched.world.clock.now() - timedelta(hours=WATCH_HOURS + 1))
    unmarked = watched.add(closed_at=None)
    watched.world.threads.threads[watched.thread.id] = replace(
        watched.thread, close_notice="failed"
    )

    watched.watch()

    assert watched.world.chat.reads == []
    assert old.id != unmarked.id


def test_only_the_five_newest_watched_threads_are_read() -> None:
    watched = Watched()
    newer = []
    for _ in range(6):
        watched.world.clock.advance(60)
        newer.append(watched.add(closed_at=watched.world.clock.now()))

    watched.watch()

    read = [ref.id for ref, _ in watched.world.chat.reads]
    assert read == [t.ref for t in reversed(newer)][:WATCH_READS_PER_FIRE]


def test_a_failed_read_ends_that_threads_watch_and_the_pass() -> None:
    watched = Watched()
    watched.world.clock.advance(60)
    second = watched.add(closed_at=watched.world.clock.now() - timedelta(seconds=1))
    first = watched.add(closed_at=watched.world.clock.now())
    watched.world.chat.read_errors[watched.ref(first).id] = ChatError("429 slow down secret")

    logs = watched.watch()

    stored = watched.stored(first)
    assert (stored.mention_notice, stored.mention_notice_at) == (
        "failed",
        watched.world.clock.now(),
    )
    assert [ref.id for ref, _ in watched.world.chat.reads] == [first.ref]
    assert watched.stored(second).mention_notice is None
    (line,) = lines(logs, "chat watch read failed")
    assert line["error_class"] == "ChatError"
    assert "secret" not in repr(logs)


def test_a_failed_read_of_a_thread_noticed_meanwhile_writes_nothing() -> None:
    watched = Watched()

    def noticed(*_: Any) -> list[Any]:
        current = watched.stored()
        watched.world.threads.threads[current.id] = replace(current, mention_notice="posted")
        raise ChatError("500")

    watched.world.chat.replies_since = noticed  # type: ignore[method-assign]

    watched.watch()

    assert watched.stored().mention_notice == "posted"


def test_no_watch_read_when_the_read_pass_failed_this_fire() -> None:
    watched = Watched()
    run = watched.world.add_run()
    open_thread = watched.world.add_thread(run)
    watched.world.chat.read_errors[watched.ref(open_thread).id] = ChatError("502")
    watched.script(a_reply(1))

    watched.poll()

    assert watched.ref(watched.thread) not in [ref for ref, _ in watched.world.chat.reads]
    assert watched.replies() == []


def test_a_cursor_moved_since_the_read_is_not_claimed_or_advanced() -> None:
    watched = Watched()
    watched.script(a_reply(1))
    real = watched.world.chat.replies_since

    def moved(thread: ThreadRef, cursor: str | None) -> list[Any]:
        replies = real(thread, cursor)
        current = watched.stored()
        watched.world.threads.threads[current.id] = replace(current, mention_cursor="c9")
        return replies

    watched.world.chat.replies_since = moved  # type: ignore[method-assign]

    watched.watch()

    assert watched.replies() == []
    assert watched.stored().mention_cursor == "c9"
    watched.script(a_reply(2, mentions_bot=False))
    watched.world.threads.threads[watched.thread.id] = replace(
        watched.stored(), mention_cursor="c1"
    )

    def moved_again(thread: ThreadRef, cursor: str | None) -> list[Any]:
        replies = real(thread, cursor)
        current = watched.stored()
        watched.world.threads.threads[current.id] = replace(current, mention_cursor="c9")
        return replies

    watched.world.chat.replies_since = moved_again  # type: ignore[method-assign]

    watched.watch()

    assert watched.stored().mention_cursor == "c9"


def test_a_failed_notice_is_failed_and_ends_the_pass() -> None:
    watched = Watched()
    watched.script(a_reply(1))
    other = watched.add(closed_at=watched.world.clock.now() - timedelta(minutes=1))
    watched.script(a_reply(1, id="r1b", cursor="c1b"), thread=other)
    sent = []

    def fail_first() -> None:
        sent.append(True)
        if len(sent) == 1:
            watched.world.chat.fail_next(ChatError("429"))

    watched.world.chat.on_send = fail_first

    logs = watched.watch()

    assert watched.stored().mention_notice == "failed"
    assert watched.stored(other).mention_notice is None
    assert len(lines(logs, "chat mention notice failed")) == 1


def test_an_internal_error_on_a_notice_fails_it_and_the_pass_goes_on() -> None:
    watched = Watched()
    watched.script(a_reply(1))
    other = watched.add(closed_at=watched.world.clock.now() - timedelta(minutes=1))
    watched.script(a_reply(1, id="r1b", cursor="c1b"), thread=other)
    sent = []

    def boom() -> None:
        sent.append(True)
        if len(sent) == 1:
            raise RuntimeError("boom")

    watched.world.chat.on_send = boom

    watched.watch()

    assert watched.stored().mention_notice == "failed"
    assert watched.stored(other).mention_notice == "posted"


def test_an_outcome_after_the_sweep_failed_the_claim_is_dropped() -> None:
    watched = Watched()
    watched.script(a_reply(1))

    def swept() -> None:
        current = watched.stored()
        watched.world.threads.threads[current.id] = replace(current, mention_notice="failed")

    watched.world.chat.on_send = swept

    logs = watched.watch()

    assert watched.stored().mention_notice == "failed"
    assert len(lines(logs, "chat mention notice outcome dropped")) == 1


def test_a_thread_without_a_root_or_failing_unexpectedly_is_skipped() -> None:
    watched = Watched()
    watched.world.threads.threads[watched.thread.id] = replace(watched.thread, ref=None)
    broken = watched.add()

    def boom(*_: Any) -> list[Any]:
        raise RuntimeError("boom")

    watched.world.chat.replies_since = boom  # type: ignore[method-assign]

    logs = watched.watch()

    assert len(lines(logs, "chat watch failed")) == 1
    assert watched.stored(broken).mention_notice is None


def test_a_failing_watch_list_is_one_line() -> None:
    watched = Watched()

    def failing(*_: Any) -> list[ChatThread]:
        raise RuntimeError("down")

    watched.world.threads.list_watched = failing  # type: ignore[method-assign]

    logs = watched.watch()

    assert len(lines(logs, "chat watch failed")) == 1


def test_no_unit_of_work_is_open_during_a_read_or_a_reply() -> None:
    watched = Watched()
    watched.script(a_reply(1))
    seen: list[bool] = []
    real = watched.world.chat.replies_since

    def reading(thread: ThreadRef, cursor: str | None) -> list[Any]:
        seen.append(watched.world.uow.is_open)
        return real(thread, cursor)

    watched.world.chat.replies_since = reading  # type: ignore[method-assign]
    watched.world.chat.on_send = lambda: seen.append(watched.world.uow.is_open)

    watched.watch()

    assert seen == [False, False]


def test_a_thread_noticed_between_the_read_and_the_claim_is_not_claimed() -> None:
    watched = Watched()
    watched.script(a_reply(1))
    real = watched.world.chat.replies_since

    def noticed(thread: ThreadRef, cursor: str | None) -> list[Any]:
        replies = real(thread, cursor)
        current = watched.stored()
        watched.world.threads.threads[current.id] = replace(current, mention_notice="posted")
        return replies

    watched.world.chat.replies_since = noticed  # type: ignore[method-assign]

    watched.watch()

    assert watched.replies() == []
    assert watched.stored().mention_cursor is None
