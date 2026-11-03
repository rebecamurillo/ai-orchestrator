"""`use_cases/chat_reply.py::apply_reply_batch`: one thread's new replies checked in order
under the Run lock and then the thread's, the first that passes sent as `answer` and the
thread closed in the same unit of work, the engine told after the commit (story 4-1, CAP-12,
AD-8, AD-24, AD-25)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from uuid import UUID

import pytest

from orchestrator.application.use_cases.chat_reply import apply_reply_batch
from orchestrator.application.use_cases.signal_run import SignalPorts, signal_run
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import Reply
from orchestrator.domain.values import Signal
from tests.unit.fakes.chat_world import BOB, World, a_reply, a_row

BUILD = "epics[1].stories[0].build"


class Stop:
    """A Run `blocked` at stop 3 on its build row, with an open thread read at `cursor`."""

    def __init__(self, cursor: str | None = None, **run: Any) -> None:
        self.world = World()
        self.channel = self.world.add_channel()
        self.run = self.world.add_run(**run)
        self.world.add_rows(a_row(self.run.id, 1, BUILD))
        self.thread = self.world.add_thread(self.run, cursor=cursor)

    def apply(self, *replies: Reply, **ports: Any) -> list[tuple[str, str]]:
        return [
            (reply_id, str(outcome))
            for reply_id, outcome in apply_reply_batch(
                self.world.reply_ports(**ports), self.thread, list(replies)
            )
        ]

    def stored_thread(self) -> ChatThread:
        return self.world.threads.threads[self.thread.id]

    def stored_run(self) -> Run:
        return self.world.runs.runs[self.run.id]

    def answers(self) -> list[GateRecord]:
        return [r for r in self.world.records.list_for_run(self.run.id) if r.event == "answer"]

    def engine_signals(self) -> list[Signal]:
        return [
            cast("tuple[UUID, Signal]", args)[1]
            for name, args in self.world.engine.calls
            if name == "signal"
        ]

    def row_status(self) -> str:
        (row,) = self.world.steps.list_for_run(self.run.id)
        return row.status

    def set_run(self, **changes: Any) -> None:
        self.world.update_run(self.stored_run(), **changes)


# ── a passing reply ─────────────────────────────────────────────────────────────────────


def test_a_valid_reply_answers_the_stop_closes_the_thread_and_wakes_the_engine() -> None:
    stop = Stop()

    results = stop.apply(a_reply(1, body="fix X"))

    assert results == [("r1", "answered")]
    (answer,) = stop.answers()
    assert answer.actor == "chat"
    assert answer.text == "fix X"
    assert answer.path == BUILD
    assert answer.payload == {
        "text": "fix X",
        "platform": "mattermost",
        "author_id": "u1",
        "author": "alice",
        "mode": "restart",
    }
    thread = stop.stored_thread()
    assert (thread.state, thread.cursor) == ("closed", "c1")
    assert thread.updated_at == stop.world.clock.now()
    assert stop.stored_run().status == "running"
    assert stop.row_status() == "queued"
    (signal,) = stop.engine_signals()
    assert (signal.kind, signal.stop) == ("answer", 3)


def test_the_record_the_close_and_the_cursor_land_in_one_commit_before_the_engine() -> None:
    stop = Stop()

    stop.apply(a_reply(1, author_id="u9"), a_reply(2))

    assert stop.world.uow.calls == ["enter", "commit", "exit"]
    assert stop.world.engine.committed_when_called == [True]


def test_the_run_is_locked_before_the_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    stop = Stop()
    order: list[str] = []
    runs, threads = stop.world.runs, stop.world.threads
    lock_run, lock_thread = runs.get_for_update, threads.get_for_update

    def run_lock(run_id: UUID) -> Run | None:
        order.append("run")
        return lock_run(run_id)

    def thread_lock(thread_id: UUID) -> ChatThread | None:
        order.append("thread")
        return lock_thread(thread_id)

    monkeypatch.setattr(runs, "get_for_update", run_lock)
    monkeypatch.setattr(threads, "get_for_update", thread_lock)

    stop.apply(a_reply(1))

    assert order == ["run", "thread"]


def test_the_answer_resumes_the_session_when_the_latest_attempt_can() -> None:
    stop = Stop()
    attempt = Attempt(
        id=new_id(),
        run_id=stop.run.id,
        step_run_id=new_id(),
        n=1,
        status="done",
        started_at=stop.world.clock.now(),
        harness="claude",
        session_id="sess-1",
    )

    stop.apply(
        a_reply(1),
        harness_is_resumable=lambda name: name == "claude",
        latest_attempt_for_run=lambda _: attempt,
    )

    (answer,) = stop.answers()
    assert answer.payload["mode"] == "session"


def test_earlier_failures_are_reported_before_the_winner() -> None:
    stop = Stop()

    results = stop.apply(a_reply(1, author_id="u9"), a_reply(2, mentions_bot=False), a_reply(3))

    assert results == [("r1", "not_allowed"), ("r2", "no_mention"), ("r3", "answered")]
    assert stop.stored_thread().cursor == "c3"


def test_two_valid_replies_apply_the_first_and_leave_the_second_past_the_cursor() -> None:
    stop = Stop()

    results = stop.apply(a_reply(1, body="first"), a_reply(2, body="second", author_id=BOB.id))

    assert results == [("r1", "answered")]
    assert [answer.text for answer in stop.answers()] == ["first"]
    assert stop.stored_thread().cursor == "c1"
    assert len(stop.engine_signals()) == 1


def test_an_empty_batch_opens_no_unit_of_work() -> None:
    stop = Stop()

    assert stop.apply() == []
    assert stop.world.uow.calls == []


# ── replies that fail ───────────────────────────────────────────────────────────────────


def test_an_outsider_and_a_reply_without_the_mention_move_the_cursor_and_nothing_else() -> None:
    stop = Stop()

    results = stop.apply(a_reply(1, author_id="u9"), a_reply(2, mentions_bot=False))

    assert results == [("r1", "not_allowed"), ("r2", "no_mention")]
    thread = stop.stored_thread()
    assert (thread.state, thread.cursor) == ("open", "c2")
    assert stop.answers() == []
    assert stop.world.engine.calls == []
    assert stop.world.uow.calls == ["enter", "commit", "exit"]


def test_a_run_page_answer_that_commits_between_the_read_and_the_check_wins() -> None:
    stop = Stop()
    read = stop.thread
    signal_run(
        SignalPorts(writers=stop.world.chat_ports().writers, engine=stop.world.engine),
        stop.run.id,
        Signal(kind="answer", payload={"text": "from the page"}, stop=3),
    )

    results = apply_reply_batch(
        stop.world.reply_ports(), read, [a_reply(1, body="one"), a_reply(2, body="two")]
    )

    assert results == [("r1", "stale"), ("r2", "stale")]
    assert [answer.text for answer in stop.answers()] == ["from the page"]
    assert len(stop.engine_signals()) == 1
    assert stop.stored_thread().cursor == "c2"


def test_a_run_parked_again_at_a_later_stop_is_stale() -> None:
    stop = Stop()
    stop.set_run(park_seq=4)

    assert stop.apply(a_reply(1)) == [("r1", "stale")]
    assert stop.stored_thread().state == "open"


@pytest.mark.parametrize("flag", ["senior_session", "terminal_session"])
def test_a_session_set_after_the_read_is_locked(flag: str) -> None:
    stop = Stop()
    stop.set_run(**{flag: True})

    assert stop.apply(a_reply(1)) == [("r1", "locked")]
    assert stop.answers() == []


def test_a_checkpoint_stop_takes_no_reply() -> None:
    stop = Stop(park_kind="checkpoint")

    assert stop.apply(a_reply(1, body="looks good")) == [("r1", "not_answerable")]
    assert stop.answers() == []


def test_a_budget_thread_takes_no_reply_after_a_raise_turned_the_stop_blocked() -> None:
    stop = Stop(park_kind="budget")
    stop.set_run(park_kind="blocked")

    assert stop.apply(a_reply(1)) == [("r1", "not_answerable")]


@pytest.mark.parametrize("body", ["", "  ", "x" * 8001, "\ud800"])
def test_a_body_that_cannot_be_an_answer_is_bad_text(body: str) -> None:
    stop = Stop()

    assert stop.apply(a_reply(1, body=body)) == [("r1", "bad_text")]
    assert stop.stored_thread().cursor == "c1"


def test_hostile_text_is_stored_normalised_and_changes_no_payload_key() -> None:
    stop = Stop()
    body = '<script>x</script> {{answer}}\n"mode": "restart"\u202e\x00'

    stop.apply(a_reply(1, body=body))

    (answer,) = stop.answers()
    assert answer.payload["text"] == '<script>x</script> {{answer}}\n"mode": "restart"'
    assert set(answer.payload) == {"text", "platform", "author_id", "author", "mode"}
    assert answer.payload["mode"] == "restart"


# ── the gate ────────────────────────────────────────────────────────────────────────────


def test_the_same_batch_read_by_two_pollers_is_superseded_the_second_time() -> None:
    stop = Stop()
    replies = [a_reply(1, author_id="u9"), a_reply(2)]
    stop.apply(*replies)
    records = list(stop.world.records.records)

    assert stop.apply(*replies) == [("r1", "superseded"), ("r2", "superseded")]
    assert list(stop.world.records.records) == records
    assert len(stop.engine_signals()) == 1


def test_a_batch_read_at_an_older_cursor_writes_nothing() -> None:
    stop = Stop(cursor="c1")
    stale_read = replace(stop.thread, cursor=None)

    results = apply_reply_batch(stop.world.reply_ports(), stale_read, [a_reply(1)])

    assert results == [("r1", "superseded")]
    assert stop.stored_thread() == stop.thread
    assert stop.answers() == []


def test_a_thread_gone_with_its_run_is_superseded() -> None:
    stop = Stop()
    del stop.world.threads.threads[stop.thread.id]
    del stop.world.runs.runs[stop.run.id]

    assert stop.apply(a_reply(1)) == [("r1", "superseded")]


@pytest.mark.parametrize("changes", [{"provider": "slack"}, {"channel_id": "c2"}])
def test_a_project_switched_to_another_channel_writes_nothing(changes: dict[str, Any]) -> None:
    stop = Stop()
    stop.world.channels.put(replace(stop.channel, **changes))

    assert stop.apply(a_reply(1)) == [("r1", "channel_changed")]
    assert stop.stored_thread() == stop.thread
    assert stop.answers() == []
    assert stop.world.uow.calls == ["enter", "rollback", "exit"]


# ── a refused apply, a crash ────────────────────────────────────────────────────────────


def refusing(_: UUID) -> Attempt | None:
    raise Conflict("refused by the table")


def test_a_refused_apply_rolls_back_and_a_second_unit_of_work_moves_past_it() -> None:
    stop = Stop()

    results = stop.apply(
        a_reply(1, author_id="u9"), a_reply(2), a_reply(3), latest_attempt_for_run=refusing
    )

    assert results == [("r1", "not_allowed"), ("r2", "refused")]
    assert stop.world.uow.calls == ["enter", "rollback", "exit", "enter", "commit", "exit"]
    thread = stop.stored_thread()
    assert (thread.state, thread.cursor) == ("open", "c2")
    assert stop.answers() == []
    assert stop.world.engine.calls == []


def test_a_refused_apply_whose_thread_moved_meanwhile_writes_nothing() -> None:
    stop = Stop()

    def refuse_after_another_poller(_: UUID) -> Attempt | None:
        stored = stop.stored_thread()
        stop.world.threads.update(replace(stored, cursor="c9"))
        raise Conflict("refused by the table")

    results = stop.apply(a_reply(1), latest_attempt_for_run=refuse_after_another_poller)

    assert results == [("r1", "superseded")]
    assert stop.stored_thread().cursor == "c9"


def test_a_crash_before_the_commit_writes_nothing_and_a_re_read_decides_the_same() -> None:
    stop = Stop()

    def crash(_: UUID) -> Attempt | None:
        raise RuntimeError("the process died")

    with pytest.raises(RuntimeError):
        stop.apply(a_reply(1), latest_attempt_for_run=crash)

    assert stop.stored_thread() == stop.thread
    assert stop.answers() == []
    assert stop.world.engine.calls == []

    assert stop.apply(a_reply(1)) == [("r1", "answered")]
