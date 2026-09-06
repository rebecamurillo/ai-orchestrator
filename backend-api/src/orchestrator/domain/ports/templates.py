"""The `TemplateVersionRepository` port: stored Template Versions, without a database.

The validator resolves a `uses: template` call by asking for the callee's stored version
(AD-15). It may not import `sqlalchemy` (AD-2), so the lookup is a `Protocol` here, an
in-memory fake in `tests/unit/fakes/templates.py`, and a SQLAlchemy adapter in
`infrastructure/db/repositories/templates.py` (3.3).

`get` answers `None` for "not stored"; deciding that a missing callee is `callee not found`
is a rule, and rules live in `application/`. The four writes and reads below are 3.3's own:

- **`add_version`** stores a version that does not exist yet (AD-15: no update, no delete).
  `description` is the parent `template` row's column, not a `TemplateVersion` field — it is
  denormalised there so `list()` never re-parses every version's YAML to answer one list.
- **`list`** answers `GET /templates`: one `TemplateSummary` per stored name.
- **`list_versions`** answers the version numbers stored under one name, ascending — both
  `GET /templates/{name}/versions` and `save_version`'s "next version" arithmetic read it.
- **`callers_of`** answers `called_by`: every `(name, version)` whose stored `calls` names
  this one, found by a repository query rather than by re-validating anything.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.entities.template import TemplateRef, TemplateSummary, TemplateVersion


@runtime_checkable
class TemplateVersionRepository(Protocol):
    """Stored Template Versions, by name and version number."""

    def get(self, name: str, version: int) -> TemplateVersion | None:
        """The stored version of this Template, or `None`."""
        ...

    def add_version(self, version: TemplateVersion, *, description: str | None) -> None:
        """Store a version that does not exist yet, and record its Template's description."""
        ...

    def list_versions(self, name: str) -> list[int]:
        """Every version number stored under this name, ascending. `[]` if none is stored."""
        ...

    def callers_of(self, name: str, version: int) -> list[TemplateRef]:
        """Every stored version whose `calls` names this `(name, version)`."""
        ...

    # Defined last: mypy resolves a bare `list[...]` written *after* this point in the class
    # body against the method below rather than the builtin (both are named `list`), so
    # every other method's `list[...]` return type is declared above it, never after.
    def list(self) -> list[TemplateSummary]:
        """Every stored Template name, its versions, and its latest description."""
        ...
