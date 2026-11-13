"""The two models refusals (epic 2 story 4, AC8)."""

from __future__ import annotations

import pytest

from orchestrator.application import findings


@pytest.mark.parametrize(
    "code", [findings.REFUSAL_MODELS_UNLISTED, findings.REFUSAL_MODELS_GATEWAY_UNREACHABLE]
)
def test_the_entry_is_a_check_refusal_with_a_guide_page(code: str) -> None:
    entry = findings.entry(code)
    assert (entry.code, entry.area, entry.source) == (code, "refusal", "check")
    assert entry.explanation
    assert findings.guide_id(code) == f"errors/{code}"
