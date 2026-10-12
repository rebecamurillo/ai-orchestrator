"""The comma-separated readers and shipped defaults `settings.py` declares its fields with."""

from __future__ import annotations

import pytest

from orchestrator.infrastructure.settings_types import (
    CLAUDE_ALLOWED_TOOLS_DEFAULT,
    LOCAL_MODELS_DEFAULT,
    READINESS_MODELS_DEFAULT,
    split_csv,
    split_pairs,
)


def test_split_csv_trims_and_drops_empty_items_and_leaves_lists_alone() -> None:
    assert split_csv(" a, b ,,c ") == ["a", "b", "c"]
    assert split_csv(["x"]) == ["x"]


def test_split_pairs_reads_name_value_pairs_and_leaves_mappings_alone() -> None:
    assert split_pairs("a=1, b = 2,") == {"a": "1", "b": "2"}
    assert split_pairs({"a": "1"}) == {"a": "1"}


@pytest.mark.parametrize("bad", ["a", "=1", "a="])
def test_split_pairs_refuses_a_pair_that_would_bind_nothing(bad: str) -> None:
    with pytest.raises(ValueError, match="not a `name=value` pair"):
        split_pairs(bad)


def test_the_shipped_defaults_are_the_documented_shapes() -> None:
    assert sorted(READINESS_MODELS_DEFAULT) == ["claude", "codex", "local"]
    assert LOCAL_MODELS_DEFAULT
    assert "Bash(git *)" in CLAUDE_ALLOWED_TOOLS_DEFAULT
