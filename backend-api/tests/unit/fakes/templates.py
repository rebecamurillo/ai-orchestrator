"""In-memory `TemplateVersionRepository` — the one fake for that port (AD-18).

Do not write another. It holds entities, not rows, keyed the way the table's primary key
will be: `(name, version)`. `add` refuses a pair it already holds, because a stored version
is immutable (AD-15) and a fake that quietly replaced one would let a caller that never
checked pass its tests and fail on the first real insert.

`add_version` (3.3) is `add` plus recording the name's description, the way the real
`template` row does — a second dict, not a second entity, because nothing here is queried
by anything but name.
"""

from __future__ import annotations

from orchestrator.domain.entities.template import TemplateRef, TemplateSummary, TemplateVersion


class FakeTemplateVersionRepository:
    """Stored Template Versions in a dictionary, keyed by `(name, version)`."""

    def __init__(self, versions: list[TemplateVersion] | None = None) -> None:
        self.versions: dict[tuple[str, int], TemplateVersion] = {}
        self.descriptions: dict[str, str | None] = {}
        for version in versions or []:
            self.add(version)

    def add(self, version: TemplateVersion) -> None:
        key = (version.name, version.version)
        if key in self.versions:
            raise ValueError(f"template {version.name}@{version.version} is already stored")
        self.versions[key] = version

    def get(self, name: str, version: int) -> TemplateVersion | None:
        return self.versions.get((name, version))

    def add_version(self, version: TemplateVersion, *, description: str | None) -> None:
        self.add(version)
        self.descriptions[version.name] = description

    def list(self) -> list[TemplateSummary]:
        names = sorted({name for name, _ in self.versions})
        summaries = []
        for name in names:
            numbers = sorted(v for (n, v) in self.versions if n == name)
            summaries.append(
                TemplateSummary(
                    name=name,
                    description=self.descriptions.get(name),
                    latest_version=max(numbers),
                    versions=tuple(numbers),
                )
            )
        return summaries

    def list_versions(self, name: str) -> list[int]:
        return sorted(v for (n, v) in self.versions if n == name)

    def callers_of(self, name: str, version: int) -> list[TemplateRef]:
        target = TemplateRef(name=name, version=version)
        callers = [
            TemplateRef(name=n, version=v)
            for (n, v), stored in self.versions.items()
            if target in stored.calls
        ]
        return sorted(callers, key=lambda ref: (ref.name, ref.version))
