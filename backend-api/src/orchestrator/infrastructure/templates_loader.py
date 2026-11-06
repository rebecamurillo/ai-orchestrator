"""Reading the shipped Template files and the operator's folder off disk (SPEC CAP-3, CAP-4).

`application/` performs no file I/O (AD-2); this is the one module that reads
`Settings.templates_dir` and `Settings.operator_templates_dir` (AD-26), handing `main.py` the
`(name, yaml_text)` pairs `seed_shipped` validates and stores, and `seed_folder` the
operator's folder through the `TemplateFolders` port.
Sorted by name so seeding is deterministic across runs of the same directory —
`seed_shipped` itself tolerates any order, but a stable order keeps its log lines and its
retry rounds reproducible.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from orchestrator.domain.ports.template_folders import FolderFile, OperatorFolder

#: The one extension a shipped Template file carries.
TEMPLATE_SUFFIX = ".yaml"


def load_shipped_templates(templates_dir: Path) -> list[tuple[str, str]]:
    """Every `*.yaml` file directly under `templates_dir`, as `(stem, text)`, name-sorted."""
    paths = sorted(templates_dir.glob(f"*{TEMPLATE_SUFFIX}"))
    return [(path.stem, path.read_text()) for path in paths]


#: The largest operator file read; a bigger one is a `read_error`, not read.
MAX_FILE_BYTES = 1024 * 1024


class FilesystemTemplateFolders:
    """`TemplateFolders` over two directories. Nothing here raises for a file's own problem."""

    def __init__(self, templates_dir: Path, operator_dir: Path | None) -> None:
        self._templates_dir = templates_dir
        self._operator_dir = operator_dir

    def shipped_names(self) -> frozenset[str]:
        return frozenset(name for name, _ in load_shipped_templates(self._templates_dir))

    def operator_stems(self) -> frozenset[str]:
        return frozenset(f.stem for f in self.operator().files if f.read_error is None)

    def operator(self) -> OperatorFolder:
        directory = self._operator_dir
        if directory is None:
            return OperatorFolder(path="", state="off")
        path = str(directory)
        try:
            entries = sorted(entry for entry in directory.iterdir() if _listed(entry.name))
        except OSError:
            return OperatorFolder(path=path, state="missing")
        return OperatorFolder(path=path, state="ready", files=tuple(_read(e) for e in entries))


def _listed(name: str) -> bool:
    return name.endswith(TEMPLATE_SUFFIX) and not name.startswith(".")


def _display(name: str) -> str:
    return os.fsencode(name).decode("utf-8", errors="backslashreplace")


def _read(path: Path) -> FolderFile:
    shown = _display(path.name)
    stem = _display(path.stem)
    try:
        path.name.encode("utf-8")
    except UnicodeEncodeError:
        return FolderFile(shown, stem, "", "file name is not UTF-8")
    try:
        info = path.stat()
        # A FIFO blocks the read and a device or `/proc` file can report size 0 and never
        # end: only a regular file is opened, and never read past the cap.
        if not stat.S_ISREG(info.st_mode):
            return FolderFile(shown, stem, "", "not a regular file")
        if info.st_size > MAX_FILE_BYTES:
            return FolderFile(shown, stem, "", "file too large")
        with path.open(encoding="utf-8") as handle:
            text = handle.read(MAX_FILE_BYTES + 1)
        if len(text.encode("utf-8")) > MAX_FILE_BYTES:
            return FolderFile(shown, stem, "", "file too large")
        return FolderFile(shown, stem, text)
    except (OSError, UnicodeDecodeError) as error:
        return FolderFile(shown, stem, "", f"{type(error).__name__}: {error}")
