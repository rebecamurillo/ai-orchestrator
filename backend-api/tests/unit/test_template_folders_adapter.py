"""`FilesystemTemplateFolders` on a temporary folder (AD-26, D13): a file's own problem is a
`read_error` on its entry, never an exception."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from orchestrator.domain.ports.template_folders import TemplateFolders
from orchestrator.infrastructure.templates_loader import (
    MAX_FILE_BYTES,
    FilesystemTemplateFolders,
)

TWO_MIB = 2 * 1024 * 1024
FILES_READ = 3


def folders(tmp_path: Path, operator: Path | None) -> FilesystemTemplateFolders:
    return FilesystemTemplateFolders(tmp_path / "shipped", operator)


def test_the_adapter_is_the_port(tmp_path: Path) -> None:
    assert isinstance(folders(tmp_path, tmp_path), TemplateFolders)


def test_an_unconfigured_folder_is_off(tmp_path: Path) -> None:
    adapter = folders(tmp_path, None)

    assert adapter.operator().state == "off"
    assert adapter.operator_stems() == frozenset()


def test_a_missing_path_and_a_path_that_is_a_file_are_missing(tmp_path: Path) -> None:
    afile = tmp_path / "afile"
    afile.write_text("x")

    assert folders(tmp_path, tmp_path / "nope").operator().state == "missing"
    assert folders(tmp_path, afile).operator().state == "missing"


def build(tmp_path: Path) -> Path:
    operator = tmp_path / "operator"
    operator.mkdir()
    (operator / "a.yaml").write_text("name: a\n")
    (operator / "inv.yaml").write_text("{ not yaml")
    (operator / "bad.yaml").write_bytes(b"\xff\xfe\x00bad")
    (operator / "d.yaml").mkdir()
    (operator / "big.yaml").write_bytes(b"#" * TWO_MIB)
    (operator / "._x.yaml").write_text("name: x\n")
    (operator / "x.yml").write_text("name: x\n")
    (operator / "notes.txt").write_text("hi")
    return operator


def test_each_file_is_read_or_carries_its_own_error(tmp_path: Path) -> None:
    folder = folders(tmp_path, build(tmp_path)).operator()

    by_file = {f.file: f for f in folder.files}
    assert folder.state == "ready"
    assert sorted(by_file) == ["a.yaml", "bad.yaml", "big.yaml", "d.yaml", "inv.yaml"]
    assert [f.file for f in folder.files] == sorted(by_file)
    assert by_file["a.yaml"].text == "name: a\n"
    assert by_file["a.yaml"].read_error is None
    assert by_file["inv.yaml"].read_error is None
    assert by_file["bad.yaml"].read_error is not None
    assert by_file["d.yaml"].read_error is not None
    assert (by_file["big.yaml"].read_error, by_file["big.yaml"].text) == ("file too large", "")
    assert TWO_MIB > MAX_FILE_BYTES


def test_operator_stems_are_the_stems_of_the_readable_files(tmp_path: Path) -> None:
    adapter = folders(tmp_path, build(tmp_path))

    assert adapter.operator_stems() == {
        f.stem for f in adapter.operator().files if not f.read_error
    }
    assert adapter.operator_stems() == {"a", "inv"}


def test_a_file_name_that_is_not_utf8_has_a_read_error_and_a_safe_display_name(
    tmp_path: Path,
) -> None:
    operator = tmp_path / "operator"
    operator.mkdir()
    raw = os.path.join(os.fsencode(operator), b"\xff.yaml")
    try:
        with open(raw, "w") as handle:
            handle.write("name: x\n")
    except OSError:
        pytest.skip("this filesystem refuses non-UTF-8 file names")

    (entry,) = folders(tmp_path, operator).operator().files

    assert entry.read_error is not None
    entry.file.encode("utf-8")
    entry.stem.encode("utf-8")
    assert "\\xff" in entry.file


def test_the_shipped_names_are_the_stems_of_the_shipped_files(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    shipped.mkdir()
    for name in ("one", "two"):
        (shipped / f"{name}.yaml").write_text(f"name: {name}\n")
    (shipped / "readme.md").write_text("x")

    assert folders(tmp_path, None).shipped_names() == {"one", "two"}
