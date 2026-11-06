"""`FilesystemTemplateFolders` on entries that are not plain files (AD-26): a FIFO, a link to a
device and a file that grows past its reported size are each a `read_error`, never a hang or
an unbounded read at start-up."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.infrastructure.templates_loader import MAX_FILE_BYTES, FilesystemTemplateFolders


def read(tmp_path: Path, operator: Path) -> dict[str, str | None]:
    folder = FilesystemTemplateFolders(tmp_path / "shipped", operator).operator()
    return {f.file: f.read_error for f in folder.files}


def test_a_fifo_is_not_opened(tmp_path: Path) -> None:
    operator = tmp_path / "operator"
    operator.mkdir()
    if not hasattr(os, "mkfifo"):
        pytest.skip("no FIFOs on this platform")
    os.mkfifo(operator / "fifo.yaml")
    (operator / "a.yaml").write_text("name: a\n")

    assert read(tmp_path, operator) == {"a.yaml": None, "fifo.yaml": "not a regular file"}


def test_a_link_to_a_device_is_not_read(tmp_path: Path) -> None:
    operator = tmp_path / "operator"
    operator.mkdir()
    if not Path("/dev/zero").exists():
        pytest.skip("no /dev/zero on this platform")
    (operator / "zero.yaml").symlink_to("/dev/zero")

    assert read(tmp_path, operator) == {"zero.yaml": "not a regular file"}


def test_a_link_to_a_regular_file_is_read(tmp_path: Path) -> None:
    operator = tmp_path / "operator"
    operator.mkdir()
    target = tmp_path / "real.yaml"
    target.write_text("name: real\n")
    (operator / "real.yaml").symlink_to(target)

    folder = FilesystemTemplateFolders(tmp_path / "shipped", operator).operator()

    assert [(f.file, f.text, f.read_error) for f in folder.files] == [
        ("real.yaml", "name: real\n", None)
    ]


def test_a_file_larger_than_its_reported_size_is_too_large(tmp_path: Path) -> None:
    operator = tmp_path / "operator"
    operator.mkdir()
    grown = operator / "grown.yaml"
    grown.write_text("#" * (MAX_FILE_BYTES + 10))
    real_stat = Path.stat

    def small_stat(self: Path, *args: object, **kwargs: object) -> os.stat_result:
        info = real_stat(self, *args, **kwargs)  # type: ignore[arg-type]
        if self.name != "grown.yaml":
            return info
        fields = list(info)
        fields[6] = 0  # st_size, as `/proc` files report it
        return os.stat_result(fields)

    with patch.object(Path, "stat", small_stat):
        assert read(tmp_path, operator) == {"grown.yaml": "file too large"}
