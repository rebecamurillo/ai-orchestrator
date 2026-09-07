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
