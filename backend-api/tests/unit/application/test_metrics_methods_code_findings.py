"""The finding methods answer only their own id (epic 6 story 2, AC8)."""

from __future__ import annotations

from orchestrator.application.analysis.findings import BUG, FINDINGS_IDS, SECURITY
from orchestrator.application.analysis.signals import RepositorySignals
from orchestrator.application.analysis.tier1a import Count
from orchestrator.application.metrics.inputs import RunInputs
from orchestrator.application.metrics.methods import REGISTRY
from orchestrator.application.metrics.methods.code import CODE_IDS


def test_both_ids_are_registered_and_kept_out_of_the_tier_1_ids() -> None:
    assert all(f"{i}@1" in REGISTRY for i in FINDINGS_IDS)
    assert not set(FINDINGS_IDS) & set(CODE_IDS)


def test_a_method_returns_only_its_own_rows() -> None:
    signals = RepositorySignals(
        path=".",
        status="ok",
        output="",
        counts=(Count(SECURITY, "high", 2, None), Count(BUG, "fixed", 1, None)),
        words={},
    )
    inputs = RunInputs.__new__(RunInputs)
    object.__setattr__(inputs, "code", (signals,))
    security = REGISTRY[f"{SECURITY}@1"](inputs)
    assert {r.metric_id for r in security} == {SECURITY}
    assert {r.metric_id for r in REGISTRY[f"{BUG}@1"](inputs)} == {BUG}
    assert [r.source for r in security] == ["high", "high"]
