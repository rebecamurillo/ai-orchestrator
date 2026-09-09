"""`RunFileOut` — `GET /runs/{id}/files` (story 6-2, SPEC CAP-2, FR-19)."""

from __future__ import annotations

from pydantic import BaseModel

from orchestrator.application.use_cases.run_files import RunFile


class RunFileOut(BaseModel):
    """`{path, content, size, mtime}` — the resolved path (a glob is expanded server-side,
    so this is never the pattern the request named), the file's whole text, its byte length
    and its `mtime` (`Workspace.mtime`'s own POSIX timestamp)."""

    path: str
    content: str
    size: int
    mtime: float

    @classmethod
    def of(cls, file: RunFile) -> RunFileOut:
        return cls(path=file.path, content=file.content, size=file.size, mtime=file.mtime)
