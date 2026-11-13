"""In-memory `PackageLookup` — the one fake for that port (AD-18). Reuse it; do not write another.

Metadata is scripted per `(ecosystem, name)`; a value that is a `LookupUnavailable` is raised.
A call whose `registry_url` is in `refuse_registries` raises `LookupUnavailable`. Every call is
recorded.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

from orchestrator.domain.ports.package_lookup import LookupUnavailable, PackageMeta, VulnReport

EMPTY_REPORT = VulnReport(frozenset(), b"", "0.0.0")


class FakePackageLookup:
    def __init__(
        self,
        metadata: Mapping[tuple[str, str], PackageMeta | LookupUnavailable] | None = None,
        vulnerabilities: VulnReport | LookupUnavailable | None = None,
        refuse_registries: Collection[str] = (),
    ) -> None:
        self._metadata = dict(metadata or {})
        self._vulnerabilities = vulnerabilities
        self._refused = set(refuse_registries)
        self.calls: list[dict[str, Any]] = []

    def vulnerabilities(self, lockfile_path: Path) -> VulnReport:
        self.calls.append({"method": "vulnerabilities", "lockfile_path": lockfile_path})
        if isinstance(self._vulnerabilities, LookupUnavailable):
            raise self._vulnerabilities
        return self._vulnerabilities or EMPTY_REPORT

    def metadata(
        self, ecosystem: str, name: str, version: str, registry_url: str | None
    ) -> PackageMeta:
        self.calls.append(
            {
                "method": "metadata",
                "ecosystem": ecosystem,
                "name": name,
                "version": version,
                "registry_url": registry_url,
            }
        )
        if registry_url is not None and registry_url in self._refused:
            raise LookupUnavailable("registry unreachable")
        answer = self._metadata.get((ecosystem, name), PackageMeta(True, None, None))
        if isinstance(answer, LookupUnavailable):
            raise answer
        return answer
