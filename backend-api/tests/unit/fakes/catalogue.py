"""In-memory `Catalogue` — the one fake for that port (AD-18). Do not write another."""

from __future__ import annotations

from typing import Any

from orchestrator.domain.ports.catalogue import Catalogue, CatalogueEntry, CatalogueMethod


class FakeCatalogue:
    """Returns the entries it was given."""

    def __init__(self, entries: tuple[CatalogueEntry, ...] = ()) -> None:
        self._entries = entries

    def entries(self) -> tuple[CatalogueEntry, ...]:
        return self._entries


def catalogue_entry(**overrides: Any) -> CatalogueEntry:
    """A valid entry; keyword overrides replace single fields."""
    fields: dict[str, Any] = {
        "id": "cost.gateway",
        "label": "gateway",
        "group": "cost",
        "level": "H",
        "scopes": ("run", "epic"),
        "unit": "USD",
        "source": "model gateway spend log",
        "component_of": None,
        "additive": "within_scope_type",
        "missing_words": ("not recorded",),
        "limits": None,
        "fingerprint_group": False,
        "methods": (CatalogueMethod(n=1, description="Sum of gateway spend.", parameters={}),),
    }
    fields.update(overrides)
    return CatalogueEntry(**fields)


assert isinstance(FakeCatalogue(), Catalogue)
