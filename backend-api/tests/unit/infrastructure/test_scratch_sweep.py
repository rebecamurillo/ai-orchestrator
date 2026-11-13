"""`sweep_analysis_scratch`: only UUID-named children of `{WORK_DIR}/analysis` go (epic 5
story 4, AC9, operator answer 2026-11-13)."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from structlog.testing import capture_logs

from orchestrator.infrastructure.analysis.scratch_sweep import sweep_analysis_scratch

LEFTOVER = str(UUID(int=7))


def warned(logs: list[dict[str, object]]) -> bool:
    return any(entry["log_level"] == "warning" for entry in logs)


def test_the_uuid_folder_goes_and_everything_else_stays(tmp_path: Path) -> None:
    work = tmp_path / "work"
    folder = work / "analysis"
    (folder / LEFTOVER / "root").mkdir(parents=True)
    (folder / LEFTOVER / "root" / "file").write_text("x")
    (folder / "not-a-uuid").mkdir()
    (folder / "stray.txt").write_text("keep")
    target = tmp_path / "outside"
    target.mkdir()
    (target / "kept").write_text("kept")
    (folder / str(UUID(int=8))).symlink_to(target, target_is_directory=True)
    (work / "wt" / "main").mkdir(parents=True)
    (work / "project" / "repo" / "base").mkdir(parents=True)

    sweep_analysis_scratch(str(work))

    assert not (folder / LEFTOVER).exists()
    assert (folder / "not-a-uuid").is_dir()
    assert (folder / "stray.txt").read_text() == "keep"
    assert (folder / str(UUID(int=8))).is_symlink()
    assert (target / "kept").read_text() == "kept"
    assert (work / "wt" / "main").is_dir()
    assert (work / "project" / "repo" / "base").is_dir()


def test_a_leftover_that_cannot_be_removed_is_logged_and_the_rest_still_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "analysis"
    stuck = folder / LEFTOVER
    stuck.mkdir(parents=True)
    other = folder / str(UUID(int=9))
    other.write_text("x")

    def refuse(path: Path) -> None:
        raise PermissionError(f"denied: {path}")

    monkeypatch.setattr("orchestrator.infrastructure.analysis.scratch_sweep.shutil.rmtree", refuse)
    with capture_logs() as logs:
        sweep_analysis_scratch(str(tmp_path))

    assert stuck.is_dir()
    assert not other.exists()
    assert warned(logs)


def test_a_uuid_named_file_is_removed(tmp_path: Path) -> None:
    folder = tmp_path / "analysis"
    folder.mkdir()
    (folder / LEFTOVER).write_text("x")

    sweep_analysis_scratch(str(tmp_path))

    assert list(folder.iterdir()) == []


@pytest.mark.parametrize("unset", [None, "", "   "])
def test_an_unset_work_dir_removes_nothing_and_warns(unset: str | None) -> None:
    with capture_logs() as logs:
        sweep_analysis_scratch(unset)

    assert warned(logs)


def test_an_absent_analysis_folder_is_not_an_error(tmp_path: Path) -> None:
    with capture_logs() as logs:
        sweep_analysis_scratch(str(tmp_path))

    assert not warned(logs)


def test_an_analysis_folder_that_is_a_symlink_outside_work_dir_is_left_alone(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / LEFTOVER).mkdir(parents=True)
    (work / "analysis").symlink_to(elsewhere, target_is_directory=True)

    with capture_logs() as logs:
        sweep_analysis_scratch(str(work))

    assert (elsewhere / LEFTOVER).is_dir()
    assert warned(logs)


def test_an_analysis_entry_that_is_a_file_is_not_a_folder_to_sweep(tmp_path: Path) -> None:
    (tmp_path / "analysis").write_text("not a folder")

    with capture_logs() as logs:
        sweep_analysis_scratch(str(tmp_path))

    assert (tmp_path / "analysis").read_text() == "not a folder"
    assert not warned(logs)
