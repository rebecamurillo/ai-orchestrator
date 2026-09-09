"""`RunFileOut.of` (story 6-2, SPEC CAP-2, FR-19) — the wire projection of `RunFile`. The
router test (`test_run_files_router.py`) proves the same shape over a real request; this is
the direct, unit-level counterpart AD-18 asks every source module to have.
"""

from __future__ import annotations

from orchestrator.api.schemas.run_files import RunFileOut
from orchestrator.application.use_cases.run_files import RunFile


def test_of_projects_every_field() -> None:
    file = RunFile(path="specs/gates/stories/2-plan.md", content="# Story\n", size=8, mtime=123.5)

    out = RunFileOut.of(file)

    assert out.model_dump() == {
        "path": "specs/gates/stories/2-plan.md",
        "content": "# Story\n",
        "size": 8,
        "mtime": 123.5,
    }
