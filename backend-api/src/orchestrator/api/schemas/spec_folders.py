"""Request and answer of `POST /spec-folders/validate` (epic 2 story 3, AD-35).

The limits are constants, not settings: a body is a spec folder's text, and nothing about an
instance changes what a folder of that size should hold.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from orchestrator.api.errors import ProblemError

MAX_FILES = 500
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024


def _unsafe(path: str) -> bool:
    return not path or path.startswith(("/", "./")) or "\\" in path or ".." in path.split("/")


class SpecFolderIn(BaseModel):
    """`{files: {path: text}}`, paths relative to the initiative folder."""

    files: dict[str, str]

    @field_validator("files")
    @classmethod
    def _within_limits(cls, files: dict[str, str]) -> dict[str, str]:
        if len(files) > MAX_FILES:
            raise ValueError(f"at most {MAX_FILES} files")
        for path in files:
            if _unsafe(path):
                raise ValueError(f"unsafe path: {path!r}")
        sizes = [len(text.encode()) for text in files.values()]
        if any(size > MAX_FILE_BYTES for size in sizes):
            raise ValueError(f"a file is over {MAX_FILE_BYTES} bytes")
        if sum(sizes) > MAX_TOTAL_BYTES:
            raise ValueError(f"more than {MAX_TOTAL_BYTES} bytes in all")
        return files


class SpecFolderCheckOut(BaseModel):
    """200: a defect is data. The findings equal what the launch check reports."""

    findings: list[ProblemError]
