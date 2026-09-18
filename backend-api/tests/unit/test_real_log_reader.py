"""`RealLogReader` (4.12): the last lines of an attempt's log file, read off disk.

`domain/ports/logs.py::LogReader` is the port; this is its one adapter, plain file I/O the
way `infrastructure/process/runner.py` is for `ProcessRunner` — outside `Workspace` on
purpose, since an attempt log lives on the container's plain filesystem, not in a Run's
worktree (see that port's own docstring).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.domain.ports.logs import LogReader
from orchestrator.infrastructure.process.logs import RealLogReader


def test_it_satisfies_the_log_reader_port() -> None:
    assert isinstance(RealLogReader(), LogReader)


def test_a_missing_path_is_no_lines() -> None:
    assert RealLogReader().tail(None, 40) == []


def test_a_file_that_does_not_exist_is_no_lines(tmp_path: Path) -> None:
    missing = tmp_path / "nope.log"

    assert RealLogReader().tail(str(missing), 40) == []


def test_a_short_file_answers_every_line(tmp_path: Path) -> None:
    log = tmp_path / "short.log"
    log.write_text("one\ntwo\nthree\n")

    assert RealLogReader().tail(str(log), 40) == ["one", "two", "three"]


def test_a_long_file_answers_only_the_last_n_lines(tmp_path: Path) -> None:
    log = tmp_path / "long.log"
    log.write_text("\n".join(f"line {i}" for i in range(100)))

    tail = RealLogReader().tail(str(log), 40)

    assert tail == [f"line {i}" for i in range(60, 100)]


def test_n_zero_is_no_lines(tmp_path: Path) -> None:
    log = tmp_path / "any.log"
    log.write_text("one\n")

    assert RealLogReader().tail(str(log), 0) == []


def test_a_file_removed_between_the_check_and_the_read_is_no_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `worktree_gc` race the adapter's own docstring names: `is_file()` and the read
    are two calls, and the file can be gone (raising `OSError`) by the second one."""
    log = tmp_path / "raced.log"
    log.write_text("one\n")

    def raise_gone(self: Path, **kwargs: object) -> str:
        raise FileNotFoundError(f"{self} vanished between the check and the read")

    monkeypatch.setattr(Path, "read_text", raise_gone)

    assert RealLogReader().tail(str(log), 40) == []


# ── read_from ────────────────────────────────────────────────────────────────


def test_read_from_first_page_returns_complete_lines(tmp_path: Path) -> None:
    """cursor=0 returns all complete lines; incomplete trailing content is withheld."""
    log = tmp_path / "a.log"
    log.write_bytes(b"line 1\nline 2\nincomplete")

    result = RealLogReader().read_from(str(log), 0, 200)

    assert result is not None
    lines, next_cursor, eof = result
    assert lines == ["line 1", "line 2"]
    assert next_cursor == len(b"line 1\nline 2\n")
    assert eof is False


def test_read_from_live_follow_returns_only_new_lines(tmp_path: Path) -> None:
    """A non-zero cursor returns only the bytes appended after that offset."""
    log = tmp_path / "b.log"
    log.write_bytes(b"line 1\nline 2\nline 3\n")
    cursor_after_line1 = len(b"line 1\n")

    result = RealLogReader().read_from(str(log), cursor_after_line1, 200)

    assert result is not None
    lines, next_cursor, eof = result
    assert lines == ["line 2", "line 3"]
    assert next_cursor == len(b"line 1\nline 2\nline 3\n")
    assert eof is True


def test_read_from_cursor_at_end_is_empty_eof_true(tmp_path: Path) -> None:
    content = b"line 1\nline 2\n"
    log = tmp_path / "c.log"
    log.write_bytes(content)

    result = RealLogReader().read_from(str(log), len(content), 200)

    assert result is not None
    lines, next_cursor, eof = result
    assert lines == []
    assert next_cursor == len(content)
    assert eof is True


def test_read_from_limit_caps_lines_and_next_cursor_is_correct(tmp_path: Path) -> None:
    """When the file has more lines than `limit`, only `limit` lines are returned and
    `next_cursor` points to the byte after the last returned line's `\\n`."""
    log = tmp_path / "d.log"
    log.write_bytes(b"line 1\nline 2\nline 3\n")

    result = RealLogReader().read_from(str(log), 0, 2)

    assert result is not None
    lines, next_cursor, eof = result
    assert lines == ["line 1", "line 2"]
    assert next_cursor == len(b"line 1\nline 2\n")
    # line 3 is still in the file
    assert eof is False


def test_read_from_incomplete_trailing_line_eof_false(tmp_path: Path) -> None:
    """A file with no trailing `\\n` returns an empty line list and eof=False."""
    log = tmp_path / "e.log"
    log.write_bytes(b"no newline here")

    result = RealLogReader().read_from(str(log), 0, 200)

    assert result is not None
    lines, next_cursor, eof = result
    assert lines == []
    assert next_cursor == 0
    assert eof is False


def test_read_from_absent_file_returns_none(tmp_path: Path) -> None:
    missing = tmp_path / "gone.log"

    assert RealLogReader().read_from(str(missing), 0, 200) is None


# ── read_raw ──────────────────────────────────────────────────────────────────


def test_read_raw_returns_full_bytes(tmp_path: Path) -> None:
    content = b"alpha\nbeta\ngamma\n"
    log = tmp_path / "f.log"
    log.write_bytes(content)

    assert RealLogReader().read_raw(str(log)) == content


def test_read_raw_absent_file_returns_none(tmp_path: Path) -> None:
    missing = tmp_path / "absent.log"

    assert RealLogReader().read_raw(str(missing)) is None
