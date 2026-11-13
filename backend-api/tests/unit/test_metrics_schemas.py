"""`api/schemas/metrics.py`: the mapper from a catalogue entry to its payload."""

from __future__ import annotations

from orchestrator.api.schemas.metrics import CatalogueEntryOut
from orchestrator.domain.ports.catalogue import CatalogueMethod
from tests.unit.fakes.catalogue import catalogue_entry


def test_from_entry_copies_every_field_and_turns_tuples_into_lists() -> None:
    entry = catalogue_entry(
        additive=False,
        missing_words=("not recorded", "not available"),
        methods=(CatalogueMethod(n=2, description="d", parameters={"k": [1]}),),
    )
    out = CatalogueEntryOut.from_entry(entry)
    assert out.model_dump() == {
        "id": "cost.gateway",
        "label": "gateway",
        "group": "cost",
        "level": "H",
        "scopes": ["run", "epic"],
        "unit": "USD",
        "source": "model gateway spend log",
        "component_of": None,
        "additive": False,
        "missing_words": ["not recorded", "not available"],
        "limits": None,
        "fingerprint_group": False,
        "methods": [{"n": 2, "description": "d", "parameters": {"k": [1]}}],
    }
