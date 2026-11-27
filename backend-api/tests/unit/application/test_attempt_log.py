"""`read_log_page` (epic 1 story 3, AD-40): why a step's log is empty or gone."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.application.use_cases.attempt_log import LogPage, read_log_page
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.runs import FakeAttemptRepository

PATH = "/logs/a.log"
ENDED = datetime(2026, 11, 20, tzinfo=UTC)
REMOVED = datetime(2026, 11, 22, tzinfo=UTC)
LIMIT = 200


def an_attempt(**overrides: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "step_run_id": new_id(),
        "n": 1,
        "status": "running",
        "log_path": PATH,
    }
    fields.update(overrides)
    return Attempt(**fields)  # type: ignore[arg-type]


def read(attempt: Attempt, raw: dict[str, bytes | None] | None = None, cursor: int = 0) -> LogPage:
    return read_log_page(
        FakeAttemptRepository([attempt]),
        FakeLogReader(raw_by_path=raw or {}),
        attempt.run_id,
        attempt.id,
        cursor=cursor,
        limit=LIMIT,
    )


def test_no_log_path_is_no_output_with_a_reason() -> None:
    page = read(an_attempt(log_path=None))

    assert page == LogPage(
        lines=[],
        next_cursor=0,
        eof=True,
        state="no_output",
        reason="no log was recorded for this attempt",
    )


def test_an_ended_attempt_with_an_empty_file_is_no_output_without_a_reason() -> None:
    page = read(an_attempt(ended_at=ENDED), {PATH: b""})

    assert page == LogPage(lines=[], next_cursor=0, eof=True, state="no_output")


def test_a_running_attempt_with_an_empty_file_is_text() -> None:
    page = read(an_attempt(), {PATH: b""})

    assert page == LogPage(lines=[], next_cursor=0, eof=True, state="text")


def test_a_running_attempt_whose_file_is_not_created_yet_is_text_and_not_eof() -> None:
    page = read(an_attempt(), {}, cursor=7)

    assert page == LogPage(lines=[], next_cursor=7, eof=False, state="text")


def test_an_ended_attempt_whose_file_is_gone_is_removed_with_the_stamp() -> None:
    page = read(an_attempt(ended_at=ENDED, log_removed_at=REMOVED))

    assert page == LogPage(
        lines=["log no longer on disk"],
        next_cursor=0,
        eof=True,
        state="removed",
        removed_at=REMOVED,
    )


def test_an_ended_attempt_whose_file_is_gone_without_a_stamp_has_no_removed_at() -> None:
    page = read(an_attempt(ended_at=ENDED))

    assert page.state == "removed"
    assert page.removed_at is None


def test_a_swept_attempt_never_closed_reads_removed_not_an_open_empty_page() -> None:
    page = read(an_attempt(log_removed_at=REMOVED))

    assert page == LogPage(
        lines=["log no longer on disk"],
        next_cursor=0,
        eof=True,
        state="removed",
        removed_at=REMOVED,
    )


@pytest.mark.parametrize("ended_at", [None, ENDED])
def test_a_file_with_lines_is_text_as_the_reader_answered(ended_at: datetime | None) -> None:
    page = read(an_attempt(ended_at=ended_at), {PATH: b"one\ntwo\npart"})

    assert page == LogPage(lines=["one", "two"], next_cursor=8, eof=False, state="text")


def test_an_ended_attempt_at_end_of_file_past_cursor_zero_is_text() -> None:
    page = read(an_attempt(ended_at=ENDED), {PATH: b"one\n"}, cursor=4)

    assert page == LogPage(lines=[], next_cursor=4, eof=True, state="text")


def test_an_attempt_of_another_run_is_not_found() -> None:
    attempt = an_attempt()

    with pytest.raises(NotFound):
        read_log_page(
            FakeAttemptRepository([attempt]),
            FakeLogReader(),
            new_id(),
            attempt.id,
            cursor=0,
            limit=LIMIT,
        )


def test_an_unknown_attempt_is_not_found() -> None:
    with pytest.raises(NotFound):
        read_log_page(
            FakeAttemptRepository(),
            FakeLogReader(),
            new_id(),
            new_id(),
            cursor=0,
            limit=LIMIT,
        )
