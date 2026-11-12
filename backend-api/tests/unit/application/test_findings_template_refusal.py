"""The `refusal-template-in-folder` entry of the findings registry (epic 2 story 2, 2026-11-12)."""

from __future__ import annotations

from orchestrator.application import findings


def test_the_template_in_folder_refusal_is_registered() -> None:
    item = findings.entry("refusal-template-in-folder")

    assert findings.REFUSAL_TEMPLATE_IN_FOLDER == "refusal-template-in-folder"
    assert item.area == "refusal"
    assert item.source == "check"
    assert item.message.strip()
    assert item.explanation.strip()
    assert findings.guide_id("refusal-template-in-folder") == "errors/refusal-template-in-folder"
