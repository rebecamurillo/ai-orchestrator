"""Every catalogued part A method is registered, and the activity constants match the catalogue."""

from __future__ import annotations

from orchestrator.application.metrics.methods import REGISTRY, activity
from orchestrator.infrastructure.metrics_catalogue import PackageCatalogue


def test_the_registry_holds_exactly_the_catalogued_first_methods() -> None:
    catalogued = {f"{e.id}@1" for e in PackageCatalogue().entries()}
    assert catalogued == {k for k in REGISTRY if k.endswith("@1")}
    assert set(REGISTRY) == catalogued


def test_the_activity_constants_equal_the_catalogue_parameters() -> None:
    entries = {e.id: e for e in PackageCatalogue().entries()}
    pause = entries["activity.pause_longest"].methods[0].parameters
    cache = entries["activity.pauses_over_cache_lifetime"].methods[0].parameters
    assert activity.MIN_GAP_SECONDS == pause["min_gap_seconds"]
    assert activity.SESSION_CACHE_SECONDS == cache["session_cache_seconds"]
    assert activity.SUBAGENT_CACHE_SECONDS == cache["subagent_cache_seconds"]
