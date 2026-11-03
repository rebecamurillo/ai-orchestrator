"""`jobs/chat_read.py::read_replies`: the read pass of `chat_poll`, one read per open thread
of the Project's current channel, each batch handed to 4-1's `apply_reply_batch`, every
failure kept on its own thread (story 4-3, CAP-12, AD-25)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from uuid import UUID

import pytest
from structlog.testing import capture_logs

from orchestrator.application.jobs import chat_read
from orchestrator.application.jobs.chat_read import INTERNAL, OUT_OF_ORDER, read_replies
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatError, ChatRateLimited, ChatThreadGone, ThreadRef
from orchestrator.domain.values import Signal
from tests.unit.fakes.chat_world import TOKEN, World, a_reply, a_row

BUILD = "epics[1].stories[0].build"
READ_FAILED = "chat read failed"
CHECKED = "chat reply checked"


class OperationalError(Exception):
    """Named as the SQL driver's is: its message carries the bound parameters."""


class Project:
    """One Project on its Mattermost channel, with `n` Runs each `blocked` at its own stop
    and an open thread there."""

    def __init__(self, n: int = 1) -> None:
        self.world = World()
        self.channel = self.world.add_channel()
        self.runs: list[Run] = []
        self.threads: list[ChatThread] = []
        for _ in range(n):
            self.add()
        self.run, self.thread = self.runs[0], self.threads[0]

    def add(self, **thread: Any) -> ChatThread:
        index = len(self.runs)
        run = self.world.add_run(park_seq=3 + index)
        self.world.add_rows(a_row(run.id, 1, BUILD))
        created = self.world.add_thread(run, created_at=self.world.clock.now(), **thread)
        self.runs.append(run)
        self.threads.append(created)
        return created

    def ref(self, thread: ChatThread) -> ThreadRef:
        assert thread.ref is not None
        return ThreadRef(id=thread.ref)

    def script(self, thread: ChatThread, *replies: Any) -> None:
        self.world.chat.script_replies(self.ref(thread), *replies)

    def fail(self, thread: ChatThread, error: Exception) -> None:
        self.world.chat.read_errors[self.ref(thread).id] = error

    def heal(self, thread: ChatThread) -> None:
        del self.world.chat.read_errors[self.ref(thread).id]

    def poll(self) -> list[dict[str, Any]]:
        with capture_logs() as logs:
            self.world.poll()
        return logs

    def read(self) -> bool:
        return read_replies(self.world.ports(), self.channel, self.world.chat, TOKEN)

    def stored(self, thread: ChatThread) -> ChatThread:
        return self.world.threads.threads[thread.id]

    def read_refs(self) -> list[str]:
        return [ref.id for ref, _ in self.world.chat.reads]

    def answers(self) -> list[GateRecord]:
        return [r for r in self.world.records.records.values() if r.event == "answer"]

    def updates(self, thread: ChatThread) -> int:
        return self.world.threads.calls.count(("update", thread.id))

    def engine_signals(self) -> list[Signal]:
        return [
            cast("tuple[UUID, Signal]", args)[1]
            for name, args in self.world.engine.calls
            if name == "signal"
        ]


def lines(logs: list[dict[str, Any]], event: str) -> list[dict[str, Any]]:
    return [line for line in logs if line["event"] == event]


# ── a reply ─────────────────────────────────────────────────────────────────────────────


def test_a_reply_from_an_allowed_person_answers_the_stop_and_is_logged() -> None:
    project = Project()
    project.script(project.thread, a_reply(1, body="fix X"))

    logs = project.poll()

    # Revised under hard rule 1(b), story 4-2, 2026-11-03: the same fire posts the closing
    # notice, and the watch then reads the closed thread from its cursor.
    ref = project.ref(project.thread)
    assert project.world.chat.reads == [(ref, None), (ref, "c1")]
    (answer,) = project.answers()
    assert (answer.actor, answer.text) == ("chat", "fix X")
    assert project.stored(project.thread).state == "closed"
    (signal,) = project.engine_signals()
    assert (signal.kind, signal.stop) == ("answer", 3)
    (line,) = lines(logs, CHECKED)
    assert line == {
        "event": CHECKED,
        "log_level": "info",
        "run_id": str(project.run.id),
        "park_seq": 3,
        "thread_id": str(project.thread.id),
        "reply_id": "r1",
        "outcome": "answered",
    }


def test_the_batch_is_read_after_the_threads_cursor_and_handed_over_with_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project()
    project.script(project.thread, a_reply(1, author_id="u9"), a_reply(2))
    project.world.threads.update(replace(project.thread, cursor="c1"))
    seen: list[tuple[str | None, list[str]]] = []
    real = chat_read.apply_reply_batch

    def spy(ports: Any, read: ChatThread, replies: Any) -> Any:
        seen.append((read.cursor, [reply.id for reply in replies]))
        return real(ports, read, replies)

    monkeypatch.setattr(chat_read, "apply_reply_batch", spy)

    project.poll()

    assert seen == [("c1", ["r2"])]


def test_the_answer_resumes_the_recorded_session_when_the_harness_can() -> None:
    project = Project()
    attempt = Attempt(
        id=new_id(),
        run_id=project.run.id,
        step_run_id=new_id(),
        n=1,
        status="done",
        started_at=project.world.clock.now(),
        harness="claude",
        session_id="sess-1",
    )
    project.world.resumable = lambda name: name == "claude"
    project.world.latest_attempt = lambda _: attempt
    project.script(project.thread, a_reply(1))

    project.poll()

    (answer,) = project.answers()
    assert answer.payload["mode"] == "session"


def test_every_checked_reply_is_one_line_with_its_outcome() -> None:
    project = Project()
    project.script(
        project.thread, a_reply(1, author_id="u9"), a_reply(2, mentions_bot=False), a_reply(3)
    )

    logs = project.poll()

    assert [(line["reply_id"], line["outcome"]) for line in lines(logs, CHECKED)] == [
        ("r1", "not_allowed"),
        ("r2", "no_mention"),
        ("r3", "answered"),
    ]


def test_the_read_pass_runs_after_the_notices() -> None:
    project = Project()
    project.world.add_record(
        project.run.id, event="senior_accept", actor="senior", payload={"files": ["t"]}
    )
    project.script(project.thread, a_reply(1))

    events = [line["event"] for line in project.poll()]

    assert events.index("chat notice posted") < events.index(CHECKED)


# ── nothing to read ─────────────────────────────────────────────────────────────────────


def test_nothing_new_writes_nothing_and_logs_nothing() -> None:
    project = Project()

    logs = project.poll()

    assert project.world.chat.reads == [(project.ref(project.thread), None)]
    assert project.updates(project.thread) == 0
    assert lines(logs, CHECKED) == lines(logs, READ_FAILED) == []
    assert project.read() is False


@pytest.mark.parametrize("off", [{"channel_id": "c2"}, {"provider": "slack"}])
def test_a_thread_on_another_channel_is_not_read(off: dict[str, str]) -> None:
    project = Project()
    other = project.add(**off)
    project.script(other, a_reply(1))

    project.poll()

    assert project.read_refs() == [project.ref(project.thread).id]
    assert project.answers() == []


def test_an_open_thread_without_a_root_is_not_read() -> None:
    project = Project()
    project.world.threads.update(replace(project.thread, ref=None))

    project.poll()

    assert project.world.chat.reads == []


def test_a_channel_that_could_not_be_opened_reads_nothing() -> None:
    project = Project()
    project.world.factory.error = ChatError("401 refused")

    project.poll()

    assert project.world.chat.reads == []


# ── a read that fails ───────────────────────────────────────────────────────────────────


def test_a_failed_read_is_kept_on_its_thread_and_the_next_thread_is_still_read() -> None:
    project = Project(2)
    first, second = project.threads
    project.fail(first, ChatError("429 Too Many Requests"))
    project.script(second, a_reply(1))

    logs = project.poll()

    assert project.read_refs() == [project.ref(first).id, project.ref(second).id]
    assert project.stored(first).error == "429 Too Many Requests"
    assert project.stored(first).state == "open"
    (line,) = lines(logs, READ_FAILED)
    assert line["thread_id"] == str(first.id)
    assert line["error"] == "429 Too Many Requests"
    assert project.stored(second).state == "closed"


def test_the_same_failure_next_fire_writes_nothing_and_logs_nothing() -> None:
    project = Project()
    project.fail(project.thread, ChatError("403 token revoked"))
    project.poll()
    writes = project.updates(project.thread)

    logs = project.poll()

    assert project.updates(project.thread) == writes
    assert lines(logs, READ_FAILED) == []


def test_a_different_failure_replaces_the_stored_one_and_is_logged() -> None:
    project = Project()
    project.fail(project.thread, ChatError("403 token revoked"))
    project.poll()
    project.fail(project.thread, ChatError("500 server error"))

    logs = project.poll()

    assert project.stored(project.thread).error == "500 server error"
    assert [line["error"] for line in lines(logs, READ_FAILED)] == ["500 server error"]


def test_the_token_is_masked_in_the_stored_and_the_logged_detail() -> None:
    project = Project()
    project.fail(project.thread, ChatError(f"401 bad token {TOKEN}"))

    logs = project.poll()

    assert project.stored(project.thread).error == "401 bad token ***"
    assert TOKEN not in str(logs)


def test_of_three_threads_the_second_failing_the_first_and_third_are_read() -> None:
    project = Project(3)
    first, second, third = project.threads
    project.fail(second, ChatError("502 bad gateway"))

    logs = project.poll()

    assert project.read_refs() == [project.ref(t).id for t in (first, second, third)]
    assert [line for line in logs if str(second.id) in str(line)] == lines(logs, READ_FAILED)
    assert len(lines(logs, READ_FAILED)) == 1


def test_a_successful_read_clears_the_stored_error() -> None:
    project = Project()
    project.fail(project.thread, ChatError("502 bad gateway"))
    project.poll()
    project.heal(project.thread)

    project.poll()

    assert project.stored(project.thread).error is None


def test_a_batch_with_no_winner_clears_the_stored_error() -> None:
    project = Project()
    project.fail(project.thread, ChatError("502 bad gateway"))
    project.poll()
    project.heal(project.thread)
    project.script(project.thread, a_reply(1, author_id="u9"))

    project.poll()

    stored = project.stored(project.thread)
    assert (stored.state, stored.cursor, stored.error) == ("open", "c1", None)


def test_an_answer_clears_the_stored_error_of_the_thread_it_closed() -> None:
    project = Project()
    project.fail(project.thread, ChatError("502 bad gateway"))
    project.poll()
    project.heal(project.thread)
    project.script(project.thread, a_reply(1))

    project.poll()

    stored = project.stored(project.thread)
    assert (stored.state, stored.error) == ("closed", None)


def test_a_failed_read_returns_true_for_the_watch_pass() -> None:
    project = Project(2)
    project.fail(project.threads[0], ChatError("502 bad gateway"))

    assert project.read() is True


def test_nothing_is_retried_within_a_fire() -> None:
    project = Project()
    project.fail(project.thread, ChatError("502 bad gateway"))

    project.poll()

    assert len(project.world.chat.reads) == 1


def test_a_thread_closed_before_its_error_is_written_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project()
    project.fail(project.thread, ChatError("502 bad gateway"))
    closed = replace(project.thread, state="closed")
    real = project.world.threads.get_for_update

    def closed_meanwhile(thread_id: UUID) -> ChatThread | None:
        project.world.threads.threads[thread_id] = closed
        return real(thread_id)

    monkeypatch.setattr(project.world.threads, "get_for_update", closed_meanwhile)

    logs = project.poll()

    assert project.stored(project.thread).error is None
    assert lines(logs, READ_FAILED) == []


def test_a_thread_gone_with_its_run_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project()
    project.fail(project.thread, ChatError("502 bad gateway"))
    monkeypatch.setattr(project.world.runs, "get_for_update", lambda run_id: None)

    logs = project.poll()

    assert project.updates(project.thread) == 0
    assert lines(logs, READ_FAILED) == []


# ── a rate limit, a deleted root, a batch out of order ─────────────────────────────────


def test_a_rate_limit_stops_the_projects_read_pass_for_this_fire() -> None:
    project = Project(3)
    first, second, third = project.threads
    project.fail(second, ChatRateLimited("conversations.replies: 429 rate limited"))
    project.script(third, a_reply(1))

    assert project.read() is True

    assert project.read_refs() == [project.ref(first).id, project.ref(second).id]
    assert project.stored(second).error == "conversations.replies: 429 rate limited"
    assert project.stored(third).state == "open"


def test_a_rate_limit_in_one_project_spares_the_next() -> None:
    project = Project()
    world = project.world
    project.fail(project.thread, ChatRateLimited("429 rate limited"))
    beta = world.add_project("Beta")
    beta_repository = world.add_repository(beta.id, "beta")
    world.add_channel(beta.id)
    run = world.add_run(project_id=beta.id, repository_id=beta_repository.id, park_seq=9)
    world.add_rows(a_row(run.id, 1, BUILD))
    beta_thread = world.add_thread(run)
    project.script(beta_thread, a_reply(1))

    project.poll()

    assert project.stored(beta_thread).state == "closed"


def test_a_deleted_root_closes_its_thread_with_the_detail() -> None:
    project = Project(2)
    gone, other = project.threads
    project.fail(gone, ChatThreadGone(f"404 Unable to find the post {TOKEN}"))
    project.script(other, a_reply(1))

    logs = project.poll()

    stored = project.stored(gone)
    assert (stored.state, stored.error) == ("closed", "404 Unable to find the post ***")
    assert stored.cursor is None
    (line,) = lines(logs, READ_FAILED)
    assert line["thread_id"] == str(gone.id)
    assert project.stored(other).state == "closed"

    project.poll()

    assert project.read_refs().count(project.ref(gone).id) == 1


def test_a_deleted_root_counts_as_a_failed_read() -> None:
    project = Project()
    project.fail(project.thread, ChatThreadGone("thread_not_found"))

    assert project.read() is True


def test_a_deleted_root_of_a_thread_closed_meanwhile_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project()
    project.fail(project.thread, ChatThreadGone("404"))
    monkeypatch.setattr(project.world.runs, "get_for_update", lambda run_id: None)

    logs = project.poll()

    assert project.updates(project.thread) == 0
    assert lines(logs, READ_FAILED) == []


def test_a_batch_out_of_order_is_a_failed_read_and_nothing_is_applied() -> None:
    project = Project()
    project.script(project.thread, a_reply(1, author_id="u9"), a_reply(2))
    project.world.chat.misordered.add(project.ref(project.thread).id)

    logs = project.poll()

    assert project.answers() == []
    stored = project.stored(project.thread)
    assert (stored.state, stored.cursor, stored.error) == ("open", None, OUT_OF_ORDER)
    (line,) = lines(logs, READ_FAILED)
    assert line["error"] == OUT_OF_ORDER
    assert lines(logs, CHECKED) == []
    assert project.read() is True


def test_a_batch_that_repeats_the_cursor_it_was_read_at_is_out_of_order() -> None:
    project = Project()
    project.script(project.thread, a_reply(1), a_reply(2))
    project.world.threads.update(replace(project.thread, cursor="c1"))
    project.world.chat.replies_since = lambda thread, cursor: [a_reply(1), a_reply(2)]  # type: ignore[method-assign]

    project.poll()

    assert project.stored(project.thread).error == OUT_OF_ORDER
    assert project.answers() == []


# ── anything else ───────────────────────────────────────────────────────────────────────


def test_an_unexpected_error_is_kept_and_logged_by_class_and_the_next_thread_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project(2)
    first, second = project.threads
    project.script(first, a_reply(1, body="SECRET reply text"))
    project.script(second, a_reply(2))
    real = chat_read.apply_reply_batch

    def broken(ports: Any, read: ChatThread, replies: Any) -> Any:
        if read.id == first.id:
            raise OperationalError("INSERT … parameters: ('SECRET reply text',)")
        return real(ports, read, replies)

    monkeypatch.setattr(chat_read, "apply_reply_batch", broken)

    logs = project.poll()

    (line,) = lines(logs, READ_FAILED)
    assert line["error"] == "internal: OperationalError"
    assert (line["run_id"], line["thread_id"]) == (str(first.run_id), str(first.id))
    assert "SECRET" not in str(logs)
    stored = project.stored(first)
    assert (stored.state, stored.error) == ("open", INTERNAL.format(name="OperationalError"))
    assert project.stored(second).state == "closed"
    assert project.read() is False

    again = project.poll()

    assert lines(again, READ_FAILED) == []


def test_an_unexpected_read_error_is_kept_and_counts_as_a_failed_read() -> None:
    project = Project()
    project.fail(project.thread, KeyError("SECRET"))

    logs = project.poll()

    assert project.stored(project.thread).error == "internal: KeyError"
    assert "SECRET" not in str(logs)
    assert project.read() is True


def test_an_error_that_cannot_even_be_kept_is_logged_and_the_pass_goes_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project(2)
    first, second = project.threads
    project.fail(first, ChatError("502 bad gateway"))
    project.script(second, a_reply(1))
    real = project.world.runs.get_for_update

    def down(run_id: UUID) -> Run | None:
        if run_id == first.run_id:
            raise OperationalError("connection lost: SECRET")
        return real(run_id)

    monkeypatch.setattr(project.world.runs, "get_for_update", down)

    logs = project.poll()

    (line,) = lines(logs, READ_FAILED)
    assert (line["thread_id"], line["error"]) == (str(first.id), "internal: OperationalError")
    assert "SECRET" not in str(logs)
    assert project.stored(second).state == "closed"


# ── overlap and hygiene ─────────────────────────────────────────────────────────────────


def test_two_fires_with_the_same_batch_answer_once(monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project()
    project.script(project.thread, a_reply(1))
    snapshot = [project.thread]
    monkeypatch.setattr(project.world.threads, "list_open_for_project", lambda _: list(snapshot))

    project.poll()
    logs = project.poll()

    assert len(project.answers()) == 1
    assert len(project.engine_signals()) == 1
    assert [line["outcome"] for line in lines(logs, CHECKED)] == ["superseded"]


def test_no_line_carries_reply_text_a_refused_author_or_the_token() -> None:
    project = Project(2)
    first, second = project.threads
    project.script(
        first,
        a_reply(1, author_id="outsider-7781", body="SECRET body", text="@bot SECRET body"),
        a_reply(2, body="SECRET answer", text="@bot SECRET answer"),
    )
    project.fail(second, ChatError(f"401 {TOKEN}"))

    logs = project.poll()

    captured = str(logs)
    for absent in ("SECRET", "outsider-7781", TOKEN):
        assert absent not in captured
    assert [line["outcome"] for line in lines(logs, CHECKED)] == ["not_allowed", "answered"]
