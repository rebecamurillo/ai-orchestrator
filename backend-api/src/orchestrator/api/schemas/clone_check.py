"""The HTTP shape of a clone check — the one place the whole result appears intact.

A new module rather than four more classes in `api/schemas/projects.py`, which is close to
the 400-line cap `tests/unit/test_source_limits.py` enforces.

**Why `RepositoryOut.clone_check` is not this shape.** `clone_check` is published as exactly
four keys, and a frozen router test compares a Repository's body against them verbatim.
FastAPI serialises every field of a response model, so a fifth key on `CloneCheckOut` would
change the body of every Repository read, checked or not. The lines and the hint are
therefore published as *siblings* of `clone_check` on a Repository, and as one whole object
on the two operations that are about a check — `POST` and
`GET /repositories/{id}/clone-check` — which is where a reader wants them together.

`hint` is derived by `CloneCheck.hint`, not carried in the payload the router was handed: one
rule, in `domain/entities/repository.py`, restated by nothing.
"""

from __future__ import annotations

from pydantic import BaseModel

from orchestrator.api.schemas.common import UtcTimestamp
from orchestrator.domain.entities.repository import (
    CloneCheck,
    CloneCheckLine,
    CloneCheckLineStatus,
    CloneCheckStatus,
)


class CloneCheckLineOut(BaseModel):
    """One command the check ran: what it was, how it went, how long, and what it said."""

    name: str
    #: Typed from the domain literal, so the generated client gets `"ok" | "failed"` and a
    #: caller can switch over it exhaustively instead of over `string`.
    status: CloneCheckLineStatus
    seconds: float
    output: str

    @classmethod
    def of(cls, line: CloneCheckLine) -> CloneCheckLineOut:
        return cls(name=line.name, status=line.status, seconds=line.seconds, output=line.output)


class CloneCheckResultOut(BaseModel):
    """The result of checking that a Repository can be reached and cloned.

    `lines` holds one entry per command the check ran, in the order they ran. `hint` is what
    the Operator can do about a failure, or empty when nothing is known. Until a check has
    run, `status` is `pending`, `at` is null and `lines` is empty.
    """

    status: CloneCheckStatus
    at: UtcTimestamp | None
    output: str
    bmad_version: str | None
    lines: list[CloneCheckLineOut]
    hint: str

    @classmethod
    def of(cls, clone_check: CloneCheck) -> CloneCheckResultOut:
        """Render a stored check. `hint` is derived here, never read from a column."""
        return cls(
            status=clone_check.status,
            at=clone_check.at,
            output=clone_check.output,
            bmad_version=clone_check.bmad_version,
            lines=[CloneCheckLineOut.of(line) for line in clone_check.lines],
            hint=clone_check.hint,
        )
