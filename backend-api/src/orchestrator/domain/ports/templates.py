"""The `TemplateVersionRepository` port: stored Template Versions, without a database.

The validator resolves a `uses: template` call by asking for the callee's stored version
(AD-15). It may not import `sqlalchemy` (AD-2), so the lookup is a `Protocol` here, an
in-memory fake in `tests/unit/fakes/templates.py`, and a SQLAlchemy adapter from 3.3.

Read-only for now: the writes belong to the story that lands storage. `get` answers `None`
for "not stored"; deciding that a missing callee is `callee not found` is a rule, and rules
live in `application/`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.entities.template import TemplateVersion


@runtime_checkable
class TemplateVersionRepository(Protocol):
    """Stored Template Versions, by name and version number."""

    def get(self, name: str, version: int) -> TemplateVersion | None:
        """The stored version of this Template, or `None`."""
        ...
