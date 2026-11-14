"""The Tier 2 methods answer only their own id (epic 6 story 1, AC10)."""

from __future__ import annotations

from orchestrator.application.analysis.signals import RepositorySignals
from orchestrator.application.analysis.tier1a import Count
from orchestrator.application.analysis.tier2 import TIER2_IDS
from orchestrator.application.metrics.inputs import RunInputs
from orchestrator.application.metrics.methods import REGISTRY
from orchestrator.application.metrics.methods.code import CODE_IDS


def test_every_tier_2_id_is_registered_and_kept_out_of_the_tier_1_ids() -> None:
    assert all(f"{i}@1" in REGISTRY for i in TIER2_IDS)
    assert not set(TIER2_IDS) & set(CODE_IDS)


def test_a_method_returns_only_its_own_rows() -> None:
    signals = RepositorySignals(
        path=".",
        status="ok",
        output="",
        counts=(
            Count("code.linter_warnings_new", None, 2, None),
            Count("code.lines_added", None, 1, None),
        ),
        words={"code.tests_executed": "n/a — tier 2 not declared"},
    )
    inputs = RunInputs.__new__(RunInputs)
    object.__setattr__(inputs, "code", (signals,))
    rows = REGISTRY["code.linter_warnings_new@1"](inputs)
    assert {r.metric_id for r in rows} == {"code.linter_warnings_new"}
    words = REGISTRY["code.tests_executed@1"](inputs)
    assert [(r.scope_type, r.missing) for r in words] == [
        ("repository", "n/a — tier 2 not declared"),
        ("run", "n/a — tier 2 not declared"),
    ]
    assert REGISTRY["code.fail_to_pass@1"](inputs) == []
