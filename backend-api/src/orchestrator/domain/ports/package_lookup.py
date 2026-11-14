"""The `PackageLookup` port: what the analysis asks the outside world about a dependency.

RM-6: only the ecosystem, the package name and its version leave the instance; no repository
path, URL or credential. Both methods raise `LookupUnavailable` when the source does not
answer. Ecosystem tokens are `npm` and `pypi`, the keys of a declaration's `registries`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable


class LookupUnavailable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class PackageMeta:
    exists: bool
    first_published: datetime | None
    licence: str | None


@dataclass(frozen=True)
class VulnReport:
    """`vulnerable` holds `(name, version)` pairs; `version` is the scanner's own."""

    vulnerable: frozenset[tuple[str, str]]
    sarif: bytes
    version: str


@runtime_checkable
class PackageLookup(Protocol):
    def vulnerabilities(self, lockfile_path: Path) -> VulnReport:
        """The known-vulnerable `(name, version)` pairs of the lock file at `lockfile_path`."""
        ...

    def metadata(
        self, ecosystem: str, name: str, version: str, registry_url: str | None
    ) -> PackageMeta:
        """What the registry says of one package; `registry_url` is a declared private one."""
        ...
