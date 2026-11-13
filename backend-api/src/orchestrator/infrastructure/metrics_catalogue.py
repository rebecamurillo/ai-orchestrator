"""The shipped metric catalogue: YAML package data read from beside the code.

The directory is package data, never a mount, so it resolves from `orchestrator.__file__` the
way `api/routers/version.py` resolves `VERSION`. An empty directory is a broken install.
"""

from __future__ import annotations

from pathlib import Path

import structlog

import orchestrator
from orchestrator.application.metrics.catalogue import validate_catalogue
from orchestrator.domain.ports.catalogue import CatalogueEntry

log = structlog.get_logger()

CATALOGUE_DIR = Path(orchestrator.__file__).resolve().parent / "metrics_catalogue"


def load_catalogue_files(directory: Path) -> list[tuple[str, str]]:
    """Every `*.yaml` in the directory, name-sorted, as `(file name, text)`."""
    return [(path.name, path.read_text()) for path in sorted(directory.glob("*.yaml"))]


class PackageCatalogue:
    """The `Catalogue` port over a directory of YAML files, validated once."""

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory
        self._entries: tuple[CatalogueEntry, ...] | None = None

    def entries(self) -> tuple[CatalogueEntry, ...]:
        if self._entries is None:
            directory = self._directory if self._directory is not None else CATALOGUE_DIR
            self._entries = validate_catalogue(load_catalogue_files(directory))
        return self._entries


def validate_shipped_catalogue() -> int:
    """The start-up check: the shipped files validate, or `CatalogueInvalid` stops start-up."""
    count = len(PackageCatalogue().entries())
    log.info("metric catalogue validated", entries=count)
    return count
