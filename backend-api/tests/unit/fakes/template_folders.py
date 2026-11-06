"""In-memory `TemplateFolders` — the one fake for that port (AD-18). Do not write another."""

from __future__ import annotations

from orchestrator.domain.ports.template_folders import FolderFile, OperatorFolder


class FakeTemplateFolders:
    """`shipped` names and the operator `folder`; counts how often `operator()` is read."""

    def __init__(
        self,
        shipped: frozenset[str] | set[str] = frozenset(),
        folder: OperatorFolder | None = None,
    ) -> None:
        self.shipped = frozenset(shipped)
        self.folder = folder if folder is not None else OperatorFolder(path="", state="off")
        self.operator_calls = 0

    def shipped_names(self) -> frozenset[str]:
        return self.shipped

    def operator_stems(self) -> frozenset[str]:
        return frozenset(f.stem for f in self.folder.files if f.read_error is None)

    def operator(self) -> OperatorFolder:
        self.operator_calls += 1
        return self.folder


def ready(*files: FolderFile, path: str = "/folder") -> OperatorFolder:
    """A `ready` folder holding these files."""
    return OperatorFolder(path=path, state="ready", files=tuple(files))


def file(name: str, text: str, read_error: str | None = None) -> FolderFile:
    """A folder file named `<name>.yaml`."""
    return FolderFile(file=f"{name}.yaml", stem=name, text=text, read_error=read_error)
