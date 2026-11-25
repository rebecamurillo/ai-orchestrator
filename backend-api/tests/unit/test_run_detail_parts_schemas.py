"""`GateRecordOut` and `SummaryOut` moved to `run_detail_parts` on line count (story 4,
epic 7); `run_views` imports them back."""

from __future__ import annotations

from orchestrator.api.schemas import run_detail_parts, run_views


def test_the_run_views_names_are_the_classes_run_detail_parts_defines() -> None:
    assert run_views.GateRecordOut is run_detail_parts.GateRecordOut
    assert run_views.SummaryOut is run_detail_parts.SummaryOut
