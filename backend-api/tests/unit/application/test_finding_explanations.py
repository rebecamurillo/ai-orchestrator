"""Every reason has one explanation paragraph, and nothing else does (story 1)."""

from __future__ import annotations

from orchestrator.application import finding_explanations
from orchestrator.application.templates import model, plan_model


def test_every_reason_has_a_non_empty_explanation_and_no_extra_key_exists() -> None:
    reasons = set(model.FINDING_REASONS + plan_model.FINDING_REASONS)
    explanations = finding_explanations.EXPLANATIONS

    assert set(explanations) == reasons
    assert all(text.strip() for text in explanations.values())
