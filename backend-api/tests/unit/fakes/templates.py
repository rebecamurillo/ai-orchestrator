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

from typing import TYPE_CHECKING

from orchestrator.domain.entities.template import TemplateRef, TemplateSummary, TemplateVersion

if TYPE_CHECKING:  # pragma: no cover — typing only
    from tests.unit.fakes.runs import FakeRunRepository


class FakeTemplateVersionRepository:
    """Stored Template Versions in a dictionary, keyed by `(name, version)`.

    `runs`, when given, is the `FakeRunRepository` `pinned_by` (4.4) counts against — read
    live at call time, so a Run a test creates after construction still counts. Omitted, as
    every caller before 4.4 omits it, `pinned_by` answers `0`: no fake pins anything.
    """

    def __init__(
        self,
        versions: list[TemplateVersion] | None = None,
        *,
        runs: FakeRunRepository | None = None,
    ) -> None:
        self.versions: dict[tuple[str, int], TemplateVersion] = {}
        self.descriptions: dict[str, str | None] = {}
        self._runs = runs
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

    def pinned_by(self, name: str, version: int) -> int:
        if self._runs is None:
            return 0
        target = TemplateRef(name=name, version=version)
        return sum(1 for run in self._runs.runs.values() if target in run.pinned_versions)
