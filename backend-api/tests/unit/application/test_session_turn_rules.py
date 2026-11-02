"""`rules/session.py`, the turns' half: numbering, resuming, the sweep, the opening line and
the reply cap (story 2-5, AD-23)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from orchestrator.application.rules import session
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ids import new_id
from tests.unit.application.writer_fixtures import build_run
from tests.unit.fakes.clock import EPOCH

RUN_ID = new_id()
ROW_ID = new_id()


def a_turn(n: int, **over: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": RUN_ID,
        "step_run_id": ROW_ID,
        "n": n,
        "status": "done",
        "role": "session",
        "started_at": EPOCH + timedelta(seconds=n),
    }
    fields.update(over)
    return Attempt(**fields)  # type: ignore[arg-type]


def test_a_turn_is_numbered_by_its_place_among_the_sessions_attempts() -> None:
    first, second, third = a_turn(4), a_turn(7), a_turn(9)

    assert session.turn_number((third, first, second), first) == 1
    assert session.turn_number((first, second, third), third) == len((first, second, third))


def test_a_turn_the_session_does_not_hold_is_numbered_after_the_last() -> None:
    held = (a_turn(4),)

    assert session.turn_number(held, a_turn(5)) == len(held) + 1


def test_a_turn_resumes_the_newest_earlier_turn_that_recorded_a_session() -> None:
    first = a_turn(4, session_id="s-1")
    second = a_turn(5, session_id="s-2")
    blank = a_turn(6, session_id="")
    current = a_turn(7)
    later = a_turn(8, session_id="s-later")

    assert session.resumable((first, second, blank, current, later), current) == "s-2"


def test_the_first_turn_resumes_nothing() -> None:
    current = a_turn(4)

    assert session.resumable((current,), current) is None


def test_only_a_turn_with_no_earlier_start_sha_sweeps() -> None:
    errored = a_turn(4, status="error")
    started = a_turn(5, start_sha="a" * 40)
    current = a_turn(6)

    assert session.needs_sweep((errored, current), current) is True
    assert session.needs_sweep((errored, started, current), current) is False


def test_the_opening_line_is_the_skill_then_values_only_then_the_text() -> None:
    line = session.opening_line(
        ("story", "specs/demo", "1", None, "blocked", "intent gap:\n  which route?"),
        "Why is the route missing?",
    )

    assert line == (
        "senior-session story specs/demo 1 - blocked intent gap: which route?\n"
        "Why is the route missing?"
    )


def test_a_blank_value_is_a_dash() -> None:
    assert session.opening_line(("run", "  ", ""), "go") == "senior-session run - -\ngo"


@pytest.mark.parametrize(
    ("text", "expected"),
    [(None, ""), ("", ""), ("short", "short"), ("é" * 40_000, "é" * 32_768)],
)
def test_a_reply_is_capped_at_64_kib(text: str | None, expected: str) -> None:
    assert session.capped(text) == expected
    assert len(session.capped(text).encode()) <= session.REPLY_LIMIT


def test_a_session_is_open_only_while_the_flag_is_set_on_a_live_run() -> None:
    assert session.session_open(build_run("needs_you", senior_session=True)) is True
    assert session.session_open(build_run("needs_you")) is False
    assert session.session_open(build_run("cancelled", senior_session=True)) is False


def test_the_turn_files_and_messages() -> None:
    assert session.REPLY_FILE == ".orchestrator/session/reply.md"
    assert session.REPLY_LIMIT == 64 * 1024
    assert session.WIP_MESSAGE == "wip: before session (orchestrator)"
    assert session.TURN_MESSAGE.format(k=2) == "session: turn 2 (orchestrator)"
