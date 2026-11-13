"""The catalogue loader and the shipped files (story 1, RM-2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.application.metrics.catalogue import CatalogueInvalid
from orchestrator.application.metrics.methods import REGISTRY
from orchestrator.domain.ports.catalogue import Catalogue
from orchestrator.infrastructure import metrics_catalogue as loader
from orchestrator.infrastructure.metrics_catalogue import (
    CATALOGUE_DIR,
    PackageCatalogue,
    load_catalogue_files,
    validate_shipped_catalogue,
)

VALID = (
    "- {id: cost.gateway, label: g, group: cost, level: H, scopes: [run], unit: USD,"
    " source: s, additive: true, missing_words: [], fingerprint_group: false,"
    " methods: [{n: 1, description: d, parameters: {}}]}\n"
)
GROUPS = {"cost", "budget", "spend", "tokens", "time", "process", "activity"}
D20_IDS = {"spend.recorded", "spend.month_recorded", "tokens.recorded_in", "tokens.recorded_out"}
# ratios the story's design notes keep out of the within_scope_type rule
NOT_SUMMABLE = {"cost.figure_gap", "cost.per_story_done", "tokens.cache_hit_share"}


def shipped() -> dict[str, object]:
    return {e.id: e for e in PackageCatalogue().entries()}


def test_load_catalogue_files_reads_yaml_only_in_name_order(tmp_path: Path) -> None:
    (tmp_path / "b.yaml").write_text("b")
    (tmp_path / "a.yaml").write_text("a")
    (tmp_path / "notes.txt").write_text("x")
    assert load_catalogue_files(tmp_path) == [("a.yaml", "a"), ("b.yaml", "b")]


def test_package_catalogue_returns_validated_entries_and_caches(tmp_path: Path) -> None:
    (tmp_path / "cost.yaml").write_text(VALID)
    catalogue = PackageCatalogue(tmp_path)
    assert isinstance(catalogue, Catalogue)
    first = catalogue.entries()
    assert [e.id for e in first] == ["cost.gateway"]
    (tmp_path / "cost.yaml").write_text("broken")
    assert catalogue.entries() is first


def test_package_catalogue_raises_on_a_bad_file(tmp_path: Path) -> None:
    (tmp_path / "cost.yaml").write_text("- {id: Bad}\n")
    with pytest.raises(CatalogueInvalid, match=r"cost\.yaml: Bad"):
        PackageCatalogue(tmp_path).entries()


def test_the_shipped_directory_holds_one_file_per_group() -> None:
    assert {p.stem for p in CATALOGUE_DIR.glob("*.yaml")} == GROUPS


def test_every_shipped_entry_has_method_one() -> None:
    for entry in PackageCatalogue().entries():
        assert entry.methods[0].n == 1, entry.id


def test_the_four_d20_ids_exist() -> None:
    assert D20_IDS <= set(shipped())


def test_component_of_rules() -> None:
    entries = shipped()
    assert entries["tokens.thinking"].component_of == "tokens.output"  # type: ignore[attr-defined]
    for key in ("tokens.cache_write_5m", "tokens.cache_write_1h"):
        assert entries[key].component_of == "tokens.cache_write"  # type: ignore[attr-defined]


def test_cost_and_token_entries_are_additive_within_scope_type() -> None:
    for entry in PackageCatalogue().entries():
        if entry.group in {"cost", "tokens"} and entry.id not in NOT_SUMMABLE:
            assert entry.additive == "within_scope_type", entry.id
    for key in NOT_SUMMABLE:
        assert shipped()[key].additive is False  # type: ignore[attr-defined]


def test_every_registered_method_names_a_catalogued_metric_and_number() -> None:
    known = {f"{e.id}@{m.n}" for e in PackageCatalogue().entries() for m in e.methods}
    assert set(REGISTRY) <= known


def test_validate_shipped_catalogue_returns_the_entry_count() -> None:
    assert validate_shipped_catalogue() == len(PackageCatalogue().entries())


def test_validate_shipped_catalogue_refuses_an_empty_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loader, "CATALOGUE_DIR", tmp_path)
    with pytest.raises(CatalogueInvalid, match="no catalogue files"):
        validate_shipped_catalogue()
