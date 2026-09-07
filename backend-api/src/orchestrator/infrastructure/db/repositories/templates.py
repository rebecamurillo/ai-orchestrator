"""The SQLAlchemy adapter for the `TemplateVersionRepository` port (SPEC CAP-3, AD-15).

It mirrors `tests/unit/fakes/templates.py`: `get` answers `None` rather than raising,
`list_versions` is ascending, and nothing here updates a stored `template_version` row —
`add_version` only ever inserts. `callers_of` scans every row and filters in Python rather
than reaching for a `jsonb` containment operator: `calls` is short and this store is not
large enough yet for the difference to matter, and a plain scan is what
`use_cases/projects.py::_refuse_duplicate_name` already does for a comparable column.

The session is the one the unit of work opened, passed in rather than looked up — see
`infrastructure/db/repositories/projects.py`'s docstring for why.

`pinned_by` (4.4) is the exception to the plain-scan rule above: it counts across the `run`
table, not this one, so it is a real `jsonb` containment query (`@>`) rather than a Python
filter over rows already in hand.

**A name PostgreSQL cannot hold matches nothing.** `template_name` arrives in a request
body, and every method that keys on it binds it into a query. PostgreSQL `text` cannot
contain a NUL byte, so psycopg refuses such a parameter before the server sees it — a
`DataError` that escapes as a 500 for what is really "no template is called that": no
stored row can hold a NUL either, because the same column would have refused the insert.
`_storable` is that fact, checked once here rather than as a validation rule repeated on
every schema that carries a Template name (the schemathesis gate found it through
`POST /runs`, which reaches this through pre-flight).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from orchestrator.domain.entities.template import TemplateRef, TemplateSummary, TemplateVersion
from orchestrator.infrastructure.db.models.run import RunRow
from orchestrator.infrastructure.db.models.template import TemplateRow, TemplateVersionRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session

#: The keys of one `calls` element, named once so the column and the entity cannot drift.
CALL_NAME_KEY = "name"
CALL_VERSION_KEY = "version"


def to_entity(row: TemplateVersionRow) -> TemplateVersion:
    """A row as the domain entity every layer above works with."""
    return TemplateVersion(
        id=row.id,
        name=row.name,
        version=row.version,
        yaml=row.yaml,
        hash=row.hash,
        calls=tuple(
            TemplateRef(name=call[CALL_NAME_KEY], version=call[CALL_VERSION_KEY])
            for call in row.calls
        ),
        created_at=row.created_at,
    )


def calls_json(version: TemplateVersion) -> list[dict[str, object]]:
    """`calls` as the `jsonb` column holds it, in the order the version pins them."""
    return [{CALL_NAME_KEY: ref.name, CALL_VERSION_KEY: ref.version} for ref in version.calls]


#: The byte a PostgreSQL `text` column cannot hold, and so a stored name cannot contain.
NUL = "\x00"


def _storable(name: str) -> bool:
    """Whether a stored `template_version.name` could equal this string at all."""
    return NUL not in name


class SQLAlchemyTemplateVersionRepository:
    """Stored Template Versions, over one open session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, name: str, version: int) -> TemplateVersion | None:
        if not _storable(name):
            return None
        row = self._session.scalars(
            select(TemplateVersionRow).where(
                TemplateVersionRow.name == name, TemplateVersionRow.version == version
            )
        ).first()
        return None if row is None else to_entity(row)

    def add_version(self, version: TemplateVersion, *, description: str | None) -> None:
        template_row = self._session.get(TemplateRow, version.name)
        if template_row is None:
            self._session.add(
                TemplateRow(
                    name=version.name,
                    description=description,
                    created_at=version.created_at,
                )
            )
        else:
            template_row.description = description
        self._session.add(
            TemplateVersionRow(
                id=version.id,
                name=version.name,
                version=version.version,
                yaml=version.yaml,
                hash=version.hash,
                calls=calls_json(version),
                created_at=version.created_at,
            )
        )

    def list(self) -> list[TemplateSummary]:
        version_rows = self._session.scalars(select(TemplateVersionRow)).all()
        descriptions = {
            row.name: row.description for row in self._session.scalars(select(TemplateRow)).all()
        }
        grouped: dict[str, list[int]] = {}
        for row in version_rows:
            grouped.setdefault(row.name, []).append(row.version)
        summaries = [
            TemplateSummary(
                name=name,
                description=descriptions.get(name),
                latest_version=max(numbers),
                versions=tuple(sorted(numbers)),
            )
            for name, numbers in grouped.items()
        ]
        summaries.sort(key=lambda summary: summary.name)
        return summaries

    def list_versions(self, name: str) -> list[int]:
        if not _storable(name):
            return []
        rows = self._session.scalars(
            select(TemplateVersionRow.version).where(TemplateVersionRow.name == name)
        ).all()
        return sorted(rows)

    def callers_of(self, name: str, version: int) -> list[TemplateRef]:
        target = {CALL_NAME_KEY: name, CALL_VERSION_KEY: version}
        rows = self._session.scalars(select(TemplateVersionRow)).all()
        callers = [
            TemplateRef(name=row.name, version=row.version) for row in rows if target in row.calls
        ]
        callers.sort(key=lambda ref: (ref.name, ref.version))
        return callers

    def pinned_by(self, name: str, version: int) -> int:
        """A `jsonb` containment query (4.4): every `run.pinned_versions` that holds this
        exact `{name, version}` pair, root or callee, whatever the Run's status."""
        if not _storable(name):
            return 0
        target = [{CALL_NAME_KEY: name, CALL_VERSION_KEY: version}]
        count = self._session.scalars(
            select(func.count()).select_from(RunRow).where(RunRow.pinned_versions.contains(target))
        ).first()
        return count or 0
