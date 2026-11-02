"""The HTTP shape of `GET /runs/{id}/session` (AD-23): the Operator's senior session."""

from __future__ import annotations

from pydantic import BaseModel

from orchestrator.application.rules.session import SessionScope
from orchestrator.application.use_cases.session_view import SessionView
from orchestrator.domain.ports.git import Change, ChangeKind


class AnchorEditOut(BaseModel):
    """One anchor the session changed, spelled as AD-17 spells a hit."""

    path: str
    kind: ChangeKind

    @classmethod
    def of(cls, change: Change) -> AnchorEditOut:
        return cls(path=change.path, kind=change.kind)


class SessionOut(BaseModel):
    """Whether a session holds the Run, whether one can start here, and what it changed."""

    active: bool
    #: True when `session_start` passes AD-13's table at this stop.
    available: bool
    #: The scopes a start at this stop has a frame for.
    scopes: list[SessionScope]
    #: The last `session_start`'s own payload, or `None` before any.
    scope: SessionScope | None
    harness: str | None
    model: str | None
    #: The open session's anchor edits, neither confirmed nor reverted yet.
    anchor_edits: list[AnchorEditOut]

    @classmethod
    def of(cls, view: SessionView) -> SessionOut:
        return cls(
            active=view.active,
            available=view.available,
            scopes=list(view.scopes),
            scope=view.scope,
            harness=view.harness,
            model=view.model,
            anchor_edits=[AnchorEditOut.of(change) for change in view.anchor_edits],
        )
