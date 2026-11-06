"""The `TemplateFolders` port: the two Template folders, read without file I/O in `domain/`.

`TEMPLATES_DIR` (the image's shipped set) and `OPERATOR_TEMPLATES_DIR` (a host folder, blank
= off) are read by `infrastructure/templates_loader.py` alone (AD-26). A file's own problem
is data on its `FolderFile`, never an exception: `application/` decides what a refused file
means.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

FolderState = Literal["off", "missing", "ready"]


@dataclass(frozen=True)
class FolderFile:
    """One `*.yaml` directly under the operator's folder."""

    #: The file's name, UTF-8-safe for display.
    file: str
    stem: str
    text: str
    #: Why the text could not be read (`None` when it was).
    read_error: str | None = None


@dataclass(frozen=True)
class OperatorFolder:
    """The operator's folder as it is now."""

    path: str
    state: FolderState
    files: tuple[FolderFile, ...] = ()


@runtime_checkable
class TemplateFolders(Protocol):
    """The shipped set's names and the operator's folder."""

    def shipped_names(self) -> frozenset[str]:
        """The stem of every shipped `*.yaml`."""
        ...

    def operator_stems(self) -> frozenset[str]:
        """The stem of every readable `*.yaml` in the operator's folder."""
        ...

    def operator(self) -> OperatorFolder:
        """One read of the operator's folder."""
        ...
