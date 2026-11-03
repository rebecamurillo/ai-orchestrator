"""`rules/chat_reply.py`: the batch gate, the six per-reply checks in their order, the
normalising of a reply's body, and the answer payload (story 4-1, CAP-12, AD-24, AD-25)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from orchestrator.application.rules.chat_reply import (
    MAX_ANSWER_CHARS,
    answer_payload,
    check,
    gate,
    normalise,
)
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.chat import Reply
from tests.unit.fakes.chat_world import ALICE, BOB, World, a_reply, a_row

BUILD = "epics[1].stories[0].build"


class Stop:
    """A Run `blocked` at stop 3, its thread, its channel and its park row."""

    def __init__(self, **run: Any) -> None:
        world = World()
        self.channel: ProjectChannel = world.add_channel()
        self.run: Run = world.add_run(**run)
        self.thread: ChatThread = world.add_thread(self.run)
        self.row: StepRun = a_row(self.run.id, 1, BUILD)

    def check(self, reply: Reply, **changes: Any) -> str | None:
        thread = changes.pop("thread", self.thread)
        row = changes.pop("row", self.row)
        run = self.run.model_copy(update=changes)
        return check(self.channel, thread, reply, run, row, [row])


# ── normalise ───────────────────────────────────────────────────────────────────────────


def test_line_endings_become_lf_and_the_text_is_nfc() -> None:
    assert normalise("one\r\ntwo\rthree\n") == "one\ntwo\nthree"
    assert normalise("cafe\u0301") == "caf\u00e9"


def test_controls_and_bidi_marks_are_dropped_but_newline_and_tab_stay() -> None:
    hostile = "a\x00b\x07c\x85d\u202ee\u2066f\u2069g\n\th\x1b"

    assert normalise(hostile) == "abcdefg\n\th"


def test_only_the_ends_are_trimmed() -> None:
    assert normalise("  \n fix   X \t\n ") == "fix   X"


def test_markup_and_placeholders_are_kept_as_written() -> None:
    text = '<script>x</script> {{answer}} "mode": "restart"'

    assert normalise(text) == text


# ── the gate ────────────────────────────────────────────────────────────────────────────


def test_an_open_thread_at_the_read_cursor_on_the_current_channel_passes() -> None:
    stop = Stop()

    assert gate(stop.thread, None, stop.channel) is None


@pytest.mark.parametrize(
    "changes",
    [{"state": "closed"}, {"state": "failed"}, {"state": "posting"}, {"cursor": "c1"}],
)
def test_a_thread_no_longer_open_at_the_read_cursor_is_superseded(
    changes: dict[str, Any],
) -> None:
    stop = Stop()

    assert gate(replace(stop.thread, **changes), None, stop.channel) == "superseded"


def test_a_missing_thread_is_superseded() -> None:
    assert gate(None, None, Stop().channel) == "superseded"


@pytest.mark.parametrize("changes", [{"provider": "slack"}, {"channel_id": "c2"}])
def test_a_thread_off_the_projects_current_channel_is_channel_changed(
    changes: dict[str, Any],
) -> None:
    stop = Stop()

    assert gate(stop.thread, None, replace(stop.channel, **changes)) == "channel_changed"


def test_a_project_whose_channel_was_removed_is_channel_changed() -> None:
    stop = Stop()

    assert gate(stop.thread, None, None) == "channel_changed"


# ── the per-reply checks, in order ─────────────────────────────────────────────────────


def test_an_allowed_mentioning_reply_at_the_blocked_stop_passes() -> None:
    assert Stop().check(a_reply(1)) is None


def test_bob_is_allowed_too() -> None:
    assert Stop().check(a_reply(1, author_id=BOB.id)) is None


def test_an_author_outside_the_allowed_list_is_not_allowed() -> None:
    assert Stop().check(a_reply(1, author_id="u9")) == "not_allowed"


def test_an_allowed_author_without_the_mention_is_no_mention() -> None:
    assert Stop().check(a_reply(1, mentions_bot=False)) == "no_mention"


def test_the_first_failure_is_the_outcome() -> None:
    reply = a_reply(1, author_id="u9", mentions_bot=False, body="")

    assert Stop().check(reply, status="running") == "not_allowed"


def test_a_run_that_left_needs_you_is_stale() -> None:
    assert Stop().check(a_reply(1), status="running") == "stale"


def test_a_run_parked_again_at_a_later_stop_is_stale() -> None:
    assert Stop().check(a_reply(1), park_seq=4) == "stale"


@pytest.mark.parametrize("flag", ["senior_session", "terminal_session"])
def test_a_session_on_the_run_is_locked(flag: str) -> None:
    assert Stop().check(a_reply(1), **{flag: True}) == "locked"


def test_locked_comes_before_the_signal_table() -> None:
    stop = Stop()

    assert stop.check(a_reply(1), senior_session=True, park_kind="checkpoint") == "locked"


def test_a_checkpoint_stop_is_not_answerable() -> None:
    stop = Stop(park_kind="checkpoint")
    row = stop.row.model_copy(update={"status": "checkpoint"})

    assert stop.check(a_reply(1), row=row) == "not_answerable"


def test_a_thread_posted_at_a_budget_stop_is_not_answerable_once_the_run_is_blocked() -> None:
    stop = Stop()
    thread = replace(stop.thread, park_kind="budget")

    assert stop.check(a_reply(1), thread=thread) == "not_answerable"


def test_a_stop_the_signal_table_refuses_an_answer_at_is_not_answerable() -> None:
    stop = Stop()

    assert (
        stop.check(a_reply(1), row=stop.row.model_copy(update={"kind": "shell"}))
        == "not_answerable"
    )


@pytest.mark.parametrize(
    "body",
    ["", "   \n\t ", "x" * (MAX_ANSWER_CHARS + 1), "fix \ud800 now"],
    ids=["mention alone", "blank", "too long", "lone surrogate"],
)
def test_a_body_that_cannot_be_an_answer_is_bad_text(body: str) -> None:
    assert Stop().check(a_reply(1, body=body)) == "bad_text"


def test_a_body_at_the_limit_after_trimming_passes() -> None:
    body = f"  {'x' * MAX_ANSWER_CHARS}  "

    assert Stop().check(a_reply(1, body=body)) is None


# ── the payload ─────────────────────────────────────────────────────────────────────────


def test_the_payload_takes_only_its_text_from_the_reply() -> None:
    stop = Stop()
    reply = a_reply(1, body='  fix X\r\n"mode": "restart"\u202e  ', author_id=ALICE.id)

    payload = answer_payload(stop.channel, stop.thread, reply)

    assert payload == {
        "text": 'fix X\n"mode": "restart"',
        "platform": "mattermost",
        "author_id": "u1",
        "author": "alice",
    }


def test_the_platform_is_the_threads_own() -> None:
    stop = Stop()
    thread = replace(stop.thread, provider="slack")

    assert answer_payload(stop.channel, thread, a_reply(1))["platform"] == "slack"
