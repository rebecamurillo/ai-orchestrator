"""The hand-named refusal entries of the findings registry (story 1.3)."""

from __future__ import annotations

from orchestrator.application import findings
from orchestrator.application.findings import (
    CODE_BY_REASON,
    REFUSAL_GUIDE_UNAVAILABLE,
    REFUSALS,
    code_for,
    entry,
    guide_id,
)


def test_the_guide_unavailable_refusal_is_registered() -> None:
    item = entry(REFUSAL_GUIDE_UNAVAILABLE)

    assert item.code == "refusal-guide-unavailable"
    assert item.area == "refusal"
    assert item.message == "guide page or schema not available"
    assert item.explanation.strip()
    assert item.source == "check"
    assert guide_id(REFUSAL_GUIDE_UNAVAILABLE) == "errors/refusal-guide-unavailable"


def test_every_refusal_is_a_refusal_and_not_a_reason_code() -> None:
    assert REFUSALS
    for code, item in REFUSALS.items():
        assert item.code == code
        assert item.area == "refusal"
        assert code.startswith("refusal-")
        assert code not in CODE_BY_REASON.values()
        assert findings.REGISTRY[code] is item


def test_a_refusal_message_is_not_a_reason() -> None:
    assert code_for("guide page or schema not available") is None
