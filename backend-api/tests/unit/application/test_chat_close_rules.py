"""`rules/chat_close.py` (story 4-2, CAP-12, AD-25): when a stop has ended, which gate record
ended it, and the words of the closing and closed-thread notices. Records are fabricated."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from orchestrator.application.rules.chat_close import (
    AUTHOR_CAP,
    WATCH_HOURS,
    WATCH_READS_PER_FIRE,
    Ending,
    close_line,
    closed_mention_line,
    ending_record,
    how,
    stop_ended,
)
from orchestrator.application.rules.chat_message import (
    MAX_POST_CHARS,
    ChatPost,
    neutralise,
    plain_length,
)
from orchestrator.application.use_cases.writers import RUN_EXPIRED
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ids import new_id
from tests.unit.fakes.chat_world import World

AT = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
RUN_ID = UUID(int=7)
OPERATOR = "by the Operator (Run page or API)"
URL = "https://orch.example.com/workflows/x"


class Log:
    """A Run's gate records in order, one second apart."""

    def __init__(self) -> None:
        self.records: list[GateRecord] = []

    def add(self, event: str, actor: str = "operator", **fields: Any) -> GateRecord:
        record = GateRecord(
            id=new_id(),
            run_id=RUN_ID,
            at=AT + timedelta(seconds=len(self.records)),
            event=event,  # type: ignore[arg-type]
            actor=actor,  # type: ignore[arg-type]
            **fields,
        )
        self.records.append(record)
        return record

    def park(self, kind: str = "blocked") -> GateRecord:
        return self.add(kind, "machine", text="why")

    def how(self, run_seq: int = 3, thread_seq: int = 3) -> str:
        return how(ending_record(self.records, run_seq, thread_seq))


def test_the_watch_constants() -> None:
    assert (WATCH_HOURS, WATCH_READS_PER_FIRE, AUTHOR_CAP) == (24, 5, 200)


# ── stop_ended ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("status", "seq", "ended"),
    [
        ("needs_you", 3, False),
        ("needs_you", 4, True),
        ("running", 3, True),
        ("queued", 3, True),
        ("done", 3, True),
        ("failed", 3, True),
        ("cancelled", 3, True),
    ],
)
def test_a_stop_ends_when_the_run_is_not_needs_you_at_its_park_seq(
    status: str, seq: int, ended: bool
) -> None:
    world = World()
    run = world.add_run(park_seq=3)
    thread = world.add_thread(run)
    moved = run.model_copy(update={"status": status, "park_seq": seq})

    assert stop_ended(moved, thread) is ended


@pytest.mark.parametrize(
    "change",
    [{"senior_session": True}, {"terminal_session": True}, {"park_kind": "blocked"}],
)
def test_a_lock_flag_or_a_park_kind_rewrite_does_not_end_the_stop(change: dict[str, Any]) -> None:
    world = World()
    run = world.add_run(park_kind="budget")
    thread = world.add_thread(run)

    assert stop_ended(run.model_copy(update=change), thread) is False


# ── ending_record ──────────────────────────────────────────────────────────────────────


def test_the_first_ending_signal_in_the_window_is_chosen() -> None:
    log = Log()
    log.park()
    log.add("budget_raise")
    chosen = log.add("answer", payload={"text": "go"})
    log.add("cancel")

    ending = ending_record(log.records, 3, 3)

    assert ending.record == chosen
    assert ending.park == log.records[0]
    assert ending.session is False


def test_the_count_back_finds_the_threads_stop_among_later_ones() -> None:
    log = Log()
    log.park()
    log.add("answer")
    log.park()
    stop_3 = log.park()
    answer = log.add("skip_story")
    log.park()
    log.add("cancel")

    ending = ending_record(log.records, 4, 3)

    assert (ending.park, ending.record) == (stop_3, answer)


def test_a_run_parked_before_park_seq_existed_counts_from_its_last_park() -> None:
    log = Log()
    for _ in range(5):
        log.park()
        log.add("continue")
    stop_0 = log.park("checkpoint")
    answer = log.add("answer")

    ending = ending_record(log.records, 0, 0)

    assert (ending.park, ending.record) == (stop_0, answer)
    assert how(ending) == f"rejected {OPERATOR}"


def test_too_few_park_records_find_no_park_and_no_ender() -> None:
    log = Log()
    log.park()
    log.add("answer")

    assert ending_record(log.records, 5, 3) == Ending(park=None, record=None)
    assert ending_record([], 0, 0) == Ending(park=None, record=None)


def test_a_thread_ahead_of_its_run_finds_nothing() -> None:
    log = Log()
    log.park()

    assert ending_record(log.records, 2, 3) == Ending(park=None, record=None)


def test_the_expiry_ranks_with_the_signals() -> None:
    log = Log()
    log.park()
    log.add("budget_raise")
    expiry = log.add("failed", "machine", text=RUN_EXPIRED)

    assert ending_record(log.records, 3, 3).record == expiry
    assert log.how() == "Run expired"


def test_a_budget_raise_comes_before_a_lifecycle_end() -> None:
    log = Log()
    log.park("budget")
    log.add("session_start")
    raise_ = log.add("budget_raise")
    log.add("cancelled", "machine")

    assert ending_record(log.records, 3, 3).record == raise_
    assert log.how() == f"budget raised {OPERATOR}"


@pytest.mark.parametrize(
    ("event", "text", "words"),
    [
        ("done", "", "the Run finished"),
        ("failed", "on_fail", "the Run failed"),
        ("cancelled", "", "the Run was cancelled"),
    ],
)
def test_a_lifecycle_end_reads_as_the_run_ending(event: str, text: str, words: str) -> None:
    log = Log()
    log.park()
    log.add("start", "machine")
    log.add(event, "machine", text=text)

    assert log.how() == words


def test_a_paused_next_park_reads_as_the_pause() -> None:
    log = Log()
    log.park()
    log.add("session_start")
    paused = log.park("paused")

    ending = ending_record(log.records, 4, 3)

    assert ending.record == paused
    assert how(ending) == "the Run was paused"


def test_a_next_park_that_is_not_a_pause_ends_nothing() -> None:
    log = Log()
    log.park()
    log.park("verify_failed")

    assert ending_record(log.records, 4, 3).record is None
    assert log.how(4, 3) == "the stop ended"


def test_no_record_in_the_window_reads_as_the_stop_ended() -> None:
    log = Log()
    log.park()
    log.add("session_start")

    assert log.how() == "the stop ended"
    assert how(Ending(park=None, record=None)) == "the stop ended"


def test_a_session_end_before_the_ender_marks_a_senior_session() -> None:
    log = Log()
    log.park()
    log.add("session_start")
    log.add("session_end")
    log.add("answer")

    assert ending_record(log.records, 3, 3).session is True
    assert log.how() == f"answered {OPERATOR} after a senior session"


def test_a_session_end_after_the_ender_does_not_count() -> None:
    log = Log()
    log.park()
    log.add("answer")
    log.add("session_end")

    assert ending_record(log.records, 3, 3).session is False


# ── how ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("event", "actor", "words"),
    [
        ("answer", "operator", f"answered {OPERATOR}"),
        ("continue", "operator", f"continued {OPERATOR}"),
        ("retry", "operator", f"retried {OPERATOR}"),
        ("skip_step", "operator", f"step skipped {OPERATOR}"),
        ("skip_story", "operator", f"story skipped {OPERATOR}"),
        ("skip_epic", "operator", f"epic skipped {OPERATOR}"),
        ("terminal_resume", "terminal", "resumed from a terminal session"),
        ("cancel", "operator", f"Run cancelled {OPERATOR}"),
        ("answer", "senior", "answered by the senior"),
        ("continue", "machine", "continued by the orchestrator"),
    ],
)
def test_a_signal_reads_as_its_verb_and_who(event: str, actor: str, words: str) -> None:
    log = Log()
    log.park()
    log.add(event, actor)

    assert log.how() == words


def test_an_answer_at_a_checkpoint_stop_reads_rejected() -> None:
    log = Log()
    log.park("checkpoint")
    log.add("answer")

    assert log.how() == f"rejected {OPERATOR}"


def test_a_chat_answer_names_its_author_and_platform() -> None:
    log = Log()
    log.park()
    log.add("answer", "chat", payload={"author": "alice", "platform": "slack", "text": "x"})

    assert log.how() == "answered by alice via slack"


@pytest.mark.parametrize("payload", [{"platform": "slack"}, {"platform": "slack", "author": ""}])
def test_a_chat_answer_without_an_author_names_a_chat_reply(payload: dict[str, Any]) -> None:
    log = Log()
    log.park()
    log.add("answer", "chat", payload=payload)

    assert log.how() == "answered by a chat reply via slack"


def test_a_hostile_author_is_neutralised_on_one_line_and_cut() -> None:
    handle = "evil\n@channel" + "x" * 300
    log = Log()
    log.park()
    log.add("answer", "chat", payload={"author": handle, "platform": "mattermost"})

    words = log.how()

    author = neutralise(handle).replace("\n", " ")[:AUTHOR_CAP]
    assert words == f"answered by {author} via mattermost"
    assert "\n" not in words


# ── close_line and closed_mention_line ─────────────────────────────────────────────────


def test_the_closing_notice_names_the_stop_how_and_carries_the_link_as_suffix() -> None:
    log = Log()
    log.park()
    log.add("answer", payload={"text": "the secret answer"})

    post = close_line(ending_record(log.records, 3, 3), 3, URL)

    assert post == ChatPost(
        f"Closed · stop 3 · answered {OPERATOR}\nReplies in this thread are no longer read.",
        f"\nRun: {URL}",
    )
    assert "secret" not in post.text


def test_the_closing_notice_without_a_base_url_has_no_link() -> None:
    post = close_line(Ending(park=None, record=None), 2, None)

    assert post == ChatPost(
        "Closed · stop 2 · the stop ended\nReplies in this thread are no longer read."
    )


def test_a_closing_notice_over_the_limit_is_cut_and_keeps_its_link() -> None:
    def wide(post: ChatPost) -> int:
        return plain_length(post) * 20

    post = close_line(Ending(park=None, record=None), 2, URL, measure=wide)

    assert wide(post) <= MAX_POST_CHARS
    assert post.suffix == f"\nRun: {URL}"
    assert post.text.startswith("Closed · stop 2")


def test_a_suffix_that_leaves_no_room_drops_the_text() -> None:
    post = close_line(Ending(park=None, record=None), 2, URL, measure=lambda _: MAX_POST_CHARS + 1)

    assert post == ChatPost("", f"\nRun: {URL}")


def test_the_closed_thread_notice_points_to_the_run_page() -> None:
    post = closed_mention_line(URL)

    assert post.text + post.suffix == f"This thread is closed. Act on the Run page: {URL}"
    assert post.suffix == f" {URL}"


def test_the_closed_thread_notice_without_a_base_url() -> None:
    assert closed_mention_line(None) == ChatPost("This thread is closed. Act on the Run page.")
