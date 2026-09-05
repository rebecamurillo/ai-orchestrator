"""In-memory `TemplateVersionRepository` — the one fake for that port (AD-18).

Do not write another. It holds entities, not rows, keyed the way the table's primary key
will be: `(name, version)`. `add` refuses a pair it already holds, because a stored version
is immutable (AD-15) and a fake that quietly replaced one would let a caller that never
checked pass its tests and fail on the first real insert.
"""

from __future__ import annotations

from orchestrator.domain.entities.template import TemplateVersion


class FakeTemplateVersionRepository:
    """Stored Template Versions in a dictionary, keyed by `(name, version)`."""

    def __init__(self, versions: list[TemplateVersion] | None = None) -> None:
        self.versions: dict[tuple[str, int], TemplateVersion] = {}
        for version in versions or []:
            self.add(version)

    def add(self, version: TemplateVersion) -> None:
        key = (version.name, version.version)
        if key in self.versions:
            raise ValueError(f"template {version.name}@{version.version} is already stored")
        self.versions[key] = version

    def get(self, name: str, version: int) -> TemplateVersion | None:
        return self.versions.get((name, version))
