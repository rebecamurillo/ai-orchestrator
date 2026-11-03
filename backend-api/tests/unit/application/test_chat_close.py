"""`jobs/chat_close.py` (story 4-2, CAP-12, AD-25): the close pass, the closing-notice pass
and the notice sweep, through `run_chat_poll` and the shared fakes. 4-1's `close_thread`
writing the close marker is pinned here too."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from structlog.testing import capture_logs

from orchestrator.application.jobs import chat_close
from orchestrator.application.jobs.chat_close import (
    close_threads,
    post_close_notices,
    sweep_notices,
)
from orchestrator.application.rules.chat_close import AUTHOR_CAP, WATCH_READS_PER_FIRE
from orchestrator.application.rules.chat_message import CONTINUATION
from orchestrator.application.use_cases.chat_reply import apply_reply_batch, close_thread
from orchestrator.application.use_cases.writers import RUN_EXPIRED
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.chat import ChatError, ChatUser, ThreadRef
from tests.unit.fakes.chat_world import ALICE, TOKEN, World, a_reply, a_row

BUILD = "epics[1].stories[0].build"
OPERATOR = "by the Operator (Run page or API)"
TAIL = "Replies in this thread are no longer read."
BACKLOG = 7
SECOND = 2


class Stop:
    """A Project on its Mattermost channel, a Run `blocked` at stop 3 with its park record,
    and the stop's open thread."""

    def __init__(self, **channel: Any) -> None:
        self.world = World()
        self.channel = self.world.add_channel(**channel)
        self.run, self.thread = self.add_stop()

    def add_stop(self, park_kind: str = "blocked", **thread: Any) -> tuple[Run, ChatThread]:
        run = self.world.add_run(park_seq=3, park_kind=park_kind)
        self.world.add_rows(a_row(run.id, 1, BUILD))
        self.record(run, park_kind, "machine", path=BUILD, text="Which schema?")
        fields = {"provider": self.channel.provider, "channel_id": self.channel.channel_id}
        fields.update(thread)
        return run, self.world.add_thread(run, **fields)

    def record(self, run: Run, event: str, actor: str = "operator", **fields: Any) -> None:
        self.world.clock.advance(1)
        self.world.add_record(run.id, event=event, actor=actor, **fields)

    def end(self, event: str = "answer", actor: str = "operator", **fields: Any) -> None:
        """The stop ends with `event`; the Run runs on."""
        self.record(self.run, event, actor, **fields)
        self.run = self.world.update_run(self.run, status=fields.pop("status", "running"))

    def move(self, run: Run, **changes: Any) -> Run:
        return self.world.update_run(run, **changes)

    def stored(self, thread: ChatThread | None = None) -> ChatThread:
        return self.world.threads.threads[(thread or self.thread).id]

    def poll(self) -> list[dict[str, Any]]:
        with capture_logs() as logs:
            self.world.poll()
        return logs

    def replies(self) -> list[str]:
        return [text for _, text in self.world.chat.replies]

    def closed_due(self, run: Run, **thread: Any) -> ChatThread:
        """A thread already closed and owing its notice."""
        fields: dict[str, Any] = {
            "state": "closed",
            "closed_at": self.world.clock.now(),
            "close_notice": "due",
            "provider": self.channel.provider,
            "channel_id": self.channel.channel_id,
        }
        fields.update(thread)
        return self.world.add_thread(run, **fields)


def lines(logs: list[dict[str, Any]], event: str) -> list[dict[str, Any]]:
    return [line for line in logs if line["event"] == event]


def notice(stop: int, how: str) -> str:
    return f"Closed · stop {stop} · {how}\n{TAIL}\nRun: https://orch.example.com/workflows/"


# ── the close marker on every close (close_thread) ──────────────────────────────────────


def test_close_thread_marks_a_thread_on_the_current_channel_as_owing_a_notice() -> None:
    stop = Stop()
    stop.world.clock.advance(60)

    close_thread(stop.world.reply_ports(), stop.thread, "c4")

    stored = stop.stored()
    assert (stored.state, stored.cursor) == ("closed", "c4")
    assert stored.closed_at == stop.world.clock.now()
    assert stored.close_notice == "due"


@pytest.mark.parametrize(
    "thread", [{"channel_id": "c-old"}, {"provider": "slack", "channel_id": "c1"}]
)
def test_close_thread_on_an_old_channel_owes_no_notice(thread: dict[str, Any]) -> None:
    stop = Stop()
    stop.world.threads.threads[stop.thread.id] = replace(stop.thread, **thread)

    close_thread(stop.world.reply_ports(), stop.stored())

    assert (stop.stored().state, stop.stored().close_notice) == ("closed", None)
    assert stop.stored().closed_at == stop.world.clock.now()


def test_close_thread_with_no_channel_owes_no_notice() -> None:
    stop = Stop()
    stop.world.channels.delete(stop.world.project.id)

    close_thread(stop.world.reply_ports(), stop.thread)

    assert stop.stored().close_notice is None


def test_close_thread_for_a_deleted_root_owes_no_notice() -> None:
    stop = Stop()

    close_thread(stop.world.reply_ports(), stop.thread, error="404 gone")

    assert (stop.stored().state, stop.stored().close_notice) == ("closed", None)


def test_close_thread_of_a_run_gone_owes_no_notice() -> None:
    stop = Stop()
    del stop.world.runs.runs[stop.run.id]

    close_thread(stop.world.reply_ports(), stop.thread)

    assert stop.stored().close_notice is None


def test_a_chat_winner_commits_the_close_marker_with_its_answer() -> None:
    stop = Stop(provider="slack")
    committed: list[tuple[str, Any]] = []
    original = stop.world.uow.commit

    def commit() -> None:
        current = stop.stored()
        committed.append((current.state, current.close_notice))
        original()

    stop.world.uow.commit = commit  # type: ignore[method-assign]

    results = apply_reply_batch(stop.world.reply_ports(), stop.thread, [a_reply(1)])

    assert results == [("r1", "answered")]
    assert committed[0] == ("closed", "due")
    assert stop.stored().closed_at == stop.world.clock.now()


# ── matrix: Run page answer, chat answer ────────────────────────────────────────────────


def test_a_run_page_answer_closes_the_thread_and_posts_one_notice_naming_the_operator() -> None:
    stop = Stop()
    stop.end("answer", payload={"text": "the secret answer"})

    stop.poll()

    stored = stop.stored()
    assert (stored.state, stored.close_notice) == ("closed", "posted")
    assert stored.close_notice_at == stop.world.clock.now()
    assert stop.replies() == [notice(3, f"answered {OPERATOR}") + str(stop.run.id)]
    assert stop.world.chat.reply_mentions == [()]
    assert (
        stop.world.chat.suffixes[-1] == f"\nRun: https://orch.example.com/workflows/{stop.run.id}"
    )
    assert "secret" not in stop.replies()[0]


def test_a_chat_answer_gets_its_notice_in_the_same_fire_and_never_again() -> None:
    stop = Stop(provider="slack")
    stop.world.chat.script_replies(_ref(stop.thread), a_reply(1, body="use B"))

    logs = stop.poll()
    stop.poll()

    assert stop.replies() == [notice(3, "answered by alice via slack") + str(stop.run.id)]
    assert stop.stored().close_notice == "posted"
    assert lines(logs, "chat thread closed") == []


def test_the_close_pass_writes_nothing_for_a_thread_4_1_closed() -> None:
    stop = Stop()
    close_thread(stop.world.reply_ports(), stop.thread, "c1")
    stop.run = stop.move(stop.run, status="running")
    before = stop.world.threads.calls.count(("update", stop.thread.id))

    close_threads(stop.world.ports())

    assert stop.world.threads.calls.count(("update", stop.thread.id)) == before


# ── matrix: other endings ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("park_kind", "event", "actor", "fields", "words"),
    [
        ("blocked", "cancel", "operator", {"status": "cancelled"}, f"Run cancelled {OPERATOR}"),
        ("blocked", "terminal_resume", "terminal", {}, "resumed from a terminal session"),
        ("dependency", "continue", "operator", {"status": "queued"}, f"continued {OPERATOR}"),
        ("blocked", "failed", "machine", {"status": "failed", "text": RUN_EXPIRED}, "Run expired"),
        ("blocked", "skip_story", "operator", {}, f"story skipped {OPERATOR}"),
        ("checkpoint", "answer", "operator", {}, f"rejected {OPERATOR}"),
    ],
)
def test_every_other_ending_is_named(
    park_kind: str, event: str, actor: str, fields: dict[str, Any], words: str
) -> None:
    stop = Stop()
    stop.run, stop.thread = stop.add_stop(park_kind=park_kind)
    stop.end(event, actor, **fields)

    stop.poll()

    assert stop.replies() == [notice(3, words) + str(stop.run.id)]


def test_a_run_failed_by_on_fail_reads_as_the_run_failing() -> None:
    stop = Stop()
    stop.record(stop.run, "retry")
    stop.record(stop.run, "failed", "machine", text="on_fail")
    stop.run = stop.move(stop.run, status="failed")

    stop.poll()

    assert stop.replies() == [notice(3, f"retried {OPERATOR}") + str(stop.run.id)]


def test_no_ender_in_the_window_reads_as_the_stop_ended() -> None:
    stop = Stop()
    stop.run = stop.move(stop.run, status="running")

    stop.poll()

    assert stop.replies() == [notice(3, "the stop ended") + str(stop.run.id)]


def test_a_senior_session_is_named_after_its_answer() -> None:
    stop = Stop()
    stop.record(stop.run, "session_start")
    stop.record(stop.run, "session_end")
    stop.end("answer")

    stop.poll()

    assert stop.replies() == [
        notice(3, f"answered {OPERATOR} after a senior session") + str(stop.run.id)
    ]


def test_a_later_stop_closes_the_earlier_thread_only() -> None:
    stop = Stop()
    stop.end("answer")
    stop.record(stop.run, "blocked", "machine", path=BUILD)
    stop.run = stop.move(stop.run, status="needs_you", park_seq=4)
    later = stop.world.add_thread(stop.run, park_seq=4, ref="root-stop-4")

    stop.poll()

    assert stop.stored().state == "closed"
    assert stop.replies() == [notice(3, f"answered {OPERATOR}") + str(stop.run.id)]
    assert (stop.stored(later).state, stop.stored(later).close_notice) == ("open", None)


@pytest.mark.parametrize(
    "change",
    [{"senior_session": True}, {"terminal_session": True}, {"park_kind": "blocked"}],
)
def test_a_stop_that_has_not_ended_stays_open(change: dict[str, Any]) -> None:
    stop = Stop()
    stop.run, stop.thread = stop.add_stop(park_kind="budget")
    stop.move(stop.run, **change)

    stop.poll()

    assert (stop.stored().state, stop.stored().close_notice) == ("open", None)


def test_the_text_is_the_same_under_metadata_only_and_the_handle_is_neutralised() -> None:
    texts = []
    for metadata_only in (False, True):
        stop = Stop(metadata_only=metadata_only, provider="slack")
        handle = "eve\n@channel" + "x" * 300
        payload = {"author": handle, "platform": "slack", "text": "answer-text"}
        stop.end("answer", "chat", payload=payload)
        stop.poll()
        (text,) = stop.replies()
        texts.append(text.rsplit("/", 1)[0])
    assert texts[0] == texts[1]
    head = texts[0].split("\n")[0]
    assert head.startswith(f"Closed · stop 3 · answered by eve {CONTINUATION}@channel")
    assert head.endswith(" via slack")
    assert len(head) <= AUTHOR_CAP + len("Closed · stop 3 · answered by  via slack")
    assert "answer-text" not in texts[0]


# ── matrix: overlap, failures, backlog ──────────────────────────────────────────────────


def test_a_second_fire_during_the_reply_writes_no_second_close_and_no_second_reply() -> None:
    stop = Stop()
    stop.end("answer")
    closes = []
    update = stop.world.threads.update

    def counting(thread: ChatThread) -> None:
        if stop.world.threads.threads[thread.id].state == "open" and thread.state == "closed":
            closes.append(thread.id)
        update(thread)

    stop.world.threads.update = counting  # type: ignore[method-assign]
    fired = []

    def second_fire() -> None:
        if not fired:
            fired.append(True)
            stop.world.poll()

    stop.world.chat.on_send = second_fire

    stop.poll()

    assert closes == [stop.thread.id]
    assert len(stop.replies()) == 1
    assert stop.stored().close_notice == "posted"


def test_a_failed_notice_is_failed_and_logged_once_and_never_reposted() -> None:
    stop = Stop()
    stop.end("answer")
    stop.world.chat.fail_next(ChatError(f"500 boom {TOKEN}"))

    logs = stop.poll()
    later = stop.poll()

    assert (stop.stored().close_notice, stop.stored().error) == ("failed", None)
    (line,) = lines(logs, "chat close notice failed")
    assert line["error_class"] == "ChatError"
    assert stop.replies() == []
    assert lines(later, "chat close notice failed") == []


def test_an_internal_error_on_a_notice_fails_it_and_the_pass_goes_on() -> None:
    stop = Stop()
    first = stop.closed_due(stop.world.add_run(status="running"))
    stop.world.clock.advance(1)
    second = stop.closed_due(stop.world.add_run(status="running"))
    sent = []

    def boom() -> None:
        sent.append(True)
        if len(sent) == 1:
            raise RuntimeError("driver said: secret")

    stop.world.chat.on_send = boom

    logs = stop.poll()

    assert stop.stored(first).close_notice == "failed"
    assert stop.stored(second).close_notice == "posted"
    (line,) = lines(logs, "chat close notice failed")
    assert line["error_class"] == "RuntimeError"


def test_a_backlog_posts_five_oldest_first_and_the_rest_next_fire() -> None:
    stop = Stop()
    due = []
    for n in range(BACKLOG):
        run = stop.world.add_run(status="running", park_seq=n)
        stop.world.clock.advance(1)
        due.append(stop.closed_due(run, closed_at=stop.world.clock.now() - timedelta(hours=n)))
    oldest = list(reversed(due))

    stop.poll()

    posted = [t for t in oldest if stop.stored(t).close_notice == "posted"]
    assert posted == oldest[:WATCH_READS_PER_FIRE]
    assert [stop.stored(t).close_notice for t in oldest[5:]] == ["due", "due"]
    assert [ref.id for ref, _ in stop.world.chat.replies] == [t.ref for t in oldest[:5]]

    stop.poll()

    assert all(stop.stored(t).close_notice == "posted" for t in due)
    assert len(stop.replies()) == BACKLOG


def test_a_429_on_the_second_notice_ends_the_pass_for_the_project() -> None:
    stop = Stop()
    due = []
    for n in range(4):
        stop.world.clock.advance(1)
        due.append(stop.closed_due(stop.world.add_run(status="running", park_seq=n)))
    sends = []

    def rate_limit_second() -> None:
        sends.append(True)
        if len(sends) == SECOND:
            stop.world.chat.fail_next(ChatError("429 too many requests"))

    stop.world.chat.on_send = rate_limit_second

    logs = stop.poll()

    assert [stop.stored(t).close_notice for t in due] == ["posted", "failed", "due", "due"]
    assert len(sends) == SECOND
    assert len(lines(logs, "chat close notice failed")) == 1


@pytest.mark.parametrize("channel", [{"channel_id": "c2"}, {"provider": "slack"}])
def test_a_due_notice_on_a_switched_channel_is_abandoned_at_the_claim(
    channel: dict[str, Any],
) -> None:
    stop = Stop()
    thread = stop.closed_due(stop.world.add_run(status="running"))
    stop.world.add_channel(**channel)

    logs = stop.poll()

    assert stop.stored(thread).close_notice == "failed"
    assert stop.replies() == []
    assert len(lines(logs, "chat close notice abandoned")) == 1


def test_a_due_notice_without_a_root_is_abandoned_at_the_claim() -> None:
    stop = Stop()
    thread = stop.closed_due(stop.world.add_run(status="running"), ref=None)

    logs = stop.poll()

    assert stop.stored(thread).close_notice == "failed"
    assert len(lines(logs, "chat close notice abandoned")) == 1


def test_a_due_notice_whose_project_turned_its_channel_off_is_failed_by_the_sweep() -> None:
    stop = Stop()
    thread = stop.closed_due(stop.world.add_run(status="running"))
    stop.world.channels.delete(stop.world.project.id)

    logs = stop.poll()

    assert stop.stored(thread).close_notice == "failed"
    assert stop.replies() == []
    assert len(lines(logs, "chat close notice abandoned")) == 1


def test_the_sweep_leaves_a_due_notice_whose_project_has_a_channel() -> None:
    stop = Stop()
    thread = stop.closed_due(stop.world.add_run(status="running"))

    sweep_notices(stop.world.ports())

    assert stop.stored(thread).close_notice == "due"


def test_the_sweep_skips_a_due_notice_claimed_or_gone_meanwhile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = Stop()
    run = stop.world.add_run(status="running")
    thread = stop.closed_due(run)
    stop.world.channels.delete(stop.world.project.id)
    stop.world.threads.threads[thread.id] = replace(thread, close_notice="sending")
    monkeypatch.setattr(
        stop.world.threads, "list_notices_in", lambda state: [thread] if state == "due" else []
    )

    sweep_notices(stop.world.ports())

    assert stop.stored(thread).close_notice == "sending"
    del stop.world.runs.runs[run.id]
    stop.world.threads.threads[thread.id] = thread

    sweep_notices(stop.world.ports())

    assert stop.stored(thread).close_notice == "failed"


@pytest.mark.parametrize("field", ["close_notice", "mention_notice"])
def test_a_notice_claimed_before_the_restart_is_failed_and_the_other_kept(field: str) -> None:
    stop = Stop()
    other = "mention_notice" if field == "close_notice" else "close_notice"
    before = stop.world.started_at - timedelta(minutes=1)
    fields: dict[str, Any] = {"close_notice": "posted", field: "sending", f"{field}_at": before}
    thread = stop.closed_due(stop.world.add_run(status="running"), **fields)
    kept = stop.stored(thread).__getattribute__(other)

    logs = stop.poll()

    assert getattr(stop.stored(thread), field) == "failed"
    assert getattr(stop.stored(thread), other) == kept
    assert stop.replies() == []
    (line,) = lines(logs, "chat notice interrupted")
    assert line["notice"] == field


def test_both_notices_claimed_before_the_restart_are_failed() -> None:
    stop = Stop()
    before = stop.world.started_at - timedelta(minutes=1)
    thread = stop.closed_due(
        stop.world.add_run(status="running"),
        close_notice="sending",
        close_notice_at=before,
        mention_notice="sending",
        mention_notice_at=None,
    )

    stop.poll()

    assert (stop.stored(thread).close_notice, stop.stored(thread).mention_notice) == (
        "failed",
        "failed",
    )


def test_a_notice_older_than_the_stale_period_is_failed() -> None:
    stop = Stop()
    thread = stop.closed_due(
        stop.world.add_run(status="running"),
        close_notice="sending",
        close_notice_at=stop.world.clock.now() - timedelta(minutes=11),
    )

    stop.poll()

    assert stop.stored(thread).close_notice == "failed"


def test_a_notice_in_flight_is_left_alone() -> None:
    stop = Stop()
    thread = stop.closed_due(
        stop.world.add_run(status="running"),
        close_notice="sending",
        close_notice_at=stop.world.clock.now() - timedelta(minutes=2),
    )

    stop.poll()

    assert stop.stored(thread).close_notice == "sending"
    assert stop.replies() == []


def test_a_notice_settled_after_the_sweep_listed_it_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = Stop()
    before = stop.world.started_at - timedelta(minutes=1)
    thread = stop.closed_due(
        stop.world.add_run(status="running"), close_notice="sending", close_notice_at=before
    )
    listed = stop.stored(thread)
    stop.world.threads.threads[thread.id] = replace(listed, close_notice="posted")
    monkeypatch.setattr(
        stop.world.threads, "list_notices_in", lambda state: [listed] if state == "sending" else []
    )

    sweep_notices(stop.world.ports())

    assert stop.stored(thread).close_notice == "posted"
    del stop.world.threads.threads[thread.id]

    sweep_notices(stop.world.ports())


def test_an_outcome_after_the_sweep_failed_the_claim_is_dropped() -> None:
    stop = Stop()
    stop.end("answer")

    def swept() -> None:
        current = stop.stored()
        stop.world.threads.threads[current.id] = replace(current, close_notice="failed")

    stop.world.chat.on_send = swept

    logs = stop.poll()

    assert stop.stored().close_notice == "failed"
    assert len(lines(logs, "chat close notice outcome dropped")) == 1


def test_a_notice_claimed_meanwhile_is_not_claimed_again() -> None:
    stop = Stop()
    thread = stop.closed_due(stop.world.add_run(status="running"))
    listed = stop.stored(thread)
    stop.world.threads.threads[thread.id] = replace(listed, close_notice="sending")
    ports = stop.world.ports()
    stop.world.threads.list_notices_due = lambda _: [listed]  # type: ignore[method-assign]

    post_close_notices(ports, stop.channel, stop.world.chat)

    assert stop.replies() == []


# ── matrix: channels ────────────────────────────────────────────────────────────────────


def test_an_open_thread_on_an_old_channel_is_closed_with_no_notice() -> None:
    stop = Stop()
    stop.world.threads.threads[stop.thread.id] = replace(stop.thread, channel_id="c-old")
    stop.end("cancel", status="cancelled")

    stop.poll()

    assert (stop.stored().state, stop.stored().close_notice) == ("closed", None)
    assert stop.replies() == []


def test_a_project_whose_channel_is_off_still_has_its_threads_closed() -> None:
    stop = Stop()
    stop.world.channels.delete(stop.world.project.id)
    stop.end("answer")

    logs = stop.poll()

    assert (stop.stored().state, stop.stored().close_notice) == ("closed", None)
    assert stop.world.factory.opened == []
    assert stop.replies() == []
    (line,) = lines(logs, "chat thread closed")
    assert line["close_notice"] is None


def test_an_unopened_channel_still_closes_and_its_notices_wait() -> None:
    stop = Stop(token_enc="never-issued")
    stop.end("answer")

    stop.poll()

    assert (stop.stored().state, stop.stored().close_notice) == ("closed", "due")
    assert stop.replies() == []


@pytest.mark.parametrize("state", ["posting", "failed"])
def test_a_thread_that_is_not_open_is_not_touched(state: str) -> None:
    stop = Stop()
    stop.world.threads.threads[stop.thread.id] = replace(stop.thread, state=state)
    stop.end("answer")

    stop.poll()

    assert (stop.stored().state, stop.stored().close_notice) == (state, None)


def test_a_stop_not_ended_takes_no_lock_and_writes_nothing() -> None:
    stop = Stop()

    close_threads(stop.world.ports())

    assert ("get", stop.run.id) in stop.world.runs.calls
    assert ("get_for_update", stop.run.id) not in stop.world.runs.calls
    assert ("update", stop.thread.id) not in stop.world.threads.calls


def test_a_thread_whose_run_is_gone_is_left(monkeypatch: pytest.MonkeyPatch) -> None:
    stop = Stop()
    del stop.world.runs.runs[stop.run.id]

    close_threads(stop.world.ports())

    assert stop.stored().state == "open"


def test_a_thread_reopened_or_resumed_under_the_lock_is_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = Stop()
    stop.end("answer")
    gets = []

    def resumed(run_id: Any) -> Run | None:
        gets.append(run_id)
        return stop.run.model_copy(update={"status": "needs_you"})

    monkeypatch.setattr(stop.world.runs, "get_for_update", resumed)

    close_threads(stop.world.ports())

    assert gets == [stop.run.id]
    assert stop.stored().state == "open"


def test_a_failing_open_list_is_one_line_and_the_project_passes_still_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = Stop()
    listing = stop.world.threads.list_by_state

    def failing(state: str) -> list[ChatThread]:
        if state == "open":
            raise RuntimeError("SELECT … 'secret'")
        return listing(state)  # type: ignore[arg-type]

    monkeypatch.setattr(stop.world.threads, "list_by_state", failing)
    stop.closed_due(stop.world.add_run(status="running"))

    logs = stop.poll()

    (line,) = lines(logs, "chat close failed")
    assert line["error_class"] == "RuntimeError"
    assert len(stop.replies()) == 1


def test_one_thread_failing_to_close_does_not_stop_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = Stop()
    stop.end("answer")
    second_run, second = stop.add_stop()
    stop.move(second_run, status="running")
    real = chat_close.close_thread
    calls = []

    def flaky(ports: Any, thread: ChatThread, *args: Any, **kwargs: Any) -> ChatThread:
        calls.append(thread.id)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return real(ports, thread, *args, **kwargs)

    monkeypatch.setattr(chat_close, "close_thread", flaky)

    with capture_logs() as logs:
        close_threads(stop.world.ports())

    assert len(calls) == SECOND
    assert stop.stored(second).state == "closed"
    assert len(lines(logs, "chat close failed")) == 1


def test_a_failing_notice_list_is_one_line(monkeypatch: pytest.MonkeyPatch) -> None:
    stop = Stop()

    def failing(_: Any) -> list[ChatThread]:
        raise RuntimeError("down")

    monkeypatch.setattr(stop.world.threads, "list_notices_due", failing)
    monkeypatch.setattr(stop.world.threads, "list_notices_in", failing)

    logs = stop.poll()

    assert len(lines(logs, "chat close notice failed")) == 1
    assert len(lines(logs, "chat notice sweep failed")) == SECOND


def test_one_sweep_item_failing_does_not_stop_the_next(monkeypatch: pytest.MonkeyPatch) -> None:
    stop = Stop()
    before = stop.world.started_at - timedelta(minutes=1)
    threads = [
        stop.closed_due(
            stop.world.add_run(status="running"), close_notice="sending", close_notice_at=before
        )
        for _ in range(2)
    ]
    get = stop.world.threads.get_for_update
    seen = []

    def flaky(thread_id: Any) -> ChatThread | None:
        seen.append(thread_id)
        if len(seen) == 1:
            raise RuntimeError("boom")
        return get(thread_id)

    monkeypatch.setattr(stop.world.threads, "get_for_update", flaky)

    with capture_logs() as logs:
        sweep_notices(stop.world.ports())

    assert stop.stored(threads[1]).close_notice == "failed"
    assert len(lines(logs, "chat notice sweep failed")) == 1


# ── matrix: no transaction, log hygiene, acceptance ─────────────────────────────────────


def test_no_unit_of_work_is_open_during_any_reply() -> None:
    stop = Stop()
    stop.end("answer")
    stop.closed_due(stop.world.add_run(status="running"))
    open_during: list[bool] = []
    stop.world.chat.on_send = lambda: open_during.append(stop.world.uow.is_open)

    stop.poll()

    assert open_during == [False, False]


def test_no_handle_author_id_token_or_error_detail_reaches_a_log_line() -> None:
    secret = ChatUser(id="u-secret-id", handle="secret-handle")
    stop = Stop(provider="slack", allowed_users=(ALICE, secret))
    stop.end(
        "answer",
        "chat",
        payload={"author": "secret-handle", "author_id": "u-secret-id", "platform": "slack"},
    )
    stop.closed_due(stop.world.add_run(status="running"))
    stop.world.chat.fail_next(ChatError(f"500 detail-secret {TOKEN}"))

    logs = stop.poll()

    text = repr(logs)
    for forbidden in ("secret-handle", "u-secret-id", TOKEN, "detail-secret"):
        assert forbidden not in text


def test_a_fire_that_raises_everywhere_returns_and_changes_no_run_step_or_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = Stop()
    stop.end("answer")
    stop.closed_due(stop.world.add_run(status="running"))
    runs = dict(stop.world.runs.runs)
    steps = dict(stop.world.steps.steps)
    records = dict(stop.world.records.records)

    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("boom")

    for name in ("get_for_update", "list_notices_due", "list_notices_in", "list_watched"):
        monkeypatch.setattr(stop.world.threads, name, boom)

    stop.poll()

    assert stop.world.runs.runs == runs
    assert stop.world.steps.steps == steps
    assert stop.world.records.records == records


def test_a_thread_closed_meanwhile_is_left_under_the_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = Stop()
    stop.end("answer")
    closed = replace(stop.thread, state="closed")
    monkeypatch.setattr(stop.world.threads, "get_for_update", lambda _: closed)

    close_threads(stop.world.ports())

    assert ("update", stop.thread.id) not in stop.world.threads.calls


def test_a_notice_that_raises_before_its_reply_is_logged_and_the_pass_goes_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = Stop()
    first = stop.closed_due(stop.world.add_run(status="running"))
    stop.world.clock.advance(1)
    second = stop.closed_due(stop.world.add_run(status="running"))
    listing = stop.world.records.list_for_run

    def flaky(run_id: Any) -> Any:
        if run_id == first.run_id:
            raise RuntimeError("SELECT … secret")
        return listing(run_id)

    monkeypatch.setattr(stop.world.records, "list_for_run", flaky)

    logs = stop.poll()

    assert stop.stored(first).close_notice == "due"
    assert stop.stored(second).close_notice == "posted"
    (line,) = lines(logs, "chat close notice failed")
    assert line["error_class"] == "RuntimeError"


def test_a_reply_batch_for_a_thread_the_close_pass_closed_is_superseded() -> None:
    stop = Stop()
    stop.end("cancel", status="cancelled")
    close_threads(stop.world.ports())

    results = apply_reply_batch(stop.world.reply_ports(), stop.thread, [a_reply(1)])

    assert results == [("r1", "superseded")]
    assert stop.stored().state == "closed"


def test_a_chat_error_ends_the_pass_even_when_its_outcome_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = Stop()
    stop.closed_due(stop.world.add_run(status="running"))
    stop.world.clock.advance(1)
    stop.closed_due(stop.world.add_run(status="running"))
    get = stop.world.threads.get_for_update
    broken: list[bool] = []
    sends: list[bool] = []

    def lock(thread_id: Any) -> ChatThread | None:
        if broken and broken.pop():
            raise RuntimeError("connection lost")
        return get(thread_id)

    def fail_first() -> None:
        sends.append(True)
        if len(sends) == 1:
            stop.world.chat.fail_next(ChatError("429"))
            broken.append(True)

    monkeypatch.setattr(stop.world.threads, "get_for_update", lock)
    stop.world.chat.on_send = fail_first

    with capture_logs() as logs:
        limited = post_close_notices(stop.world.ports(), stop.channel, stop.world.chat)

    assert limited is True
    assert len(sends) == 1
    (line,) = lines(logs, "chat close notice failed")
    assert line["error_class"] == "RuntimeError"


def _ref(thread: ChatThread) -> ThreadRef:
    assert thread.ref is not None
    return ThreadRef(id=thread.ref)
