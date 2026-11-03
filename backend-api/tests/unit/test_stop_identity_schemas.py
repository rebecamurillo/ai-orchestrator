"""AD-24 at the HTTP shape: `stop` on the way in, `park_seq` on the way out."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.api.schemas.run_events import RunEventsOut
from orchestrator.api.schemas.run_views import RunDetailSummaryOut
from orchestrator.api.schemas.runs import RunSummaryOut
from orchestrator.api.schemas.signals import SignalIn
from orchestrator.application.use_cases.run_events import RunEvent
from tests.unit.application.writer_fixtures import build_run

STOP = 3
AT = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def test_a_signal_body_passes_its_stop_on() -> None:
    assert SignalIn(kind="answer", stop=STOP).as_signal().stop == STOP


def test_a_signal_body_without_a_stop_names_none() -> None:
    assert SignalIn(kind="answer").as_signal().stop is None


def test_the_contract_keeps_stop_and_park_seq_optional() -> None:
    assert "stop" not in SignalIn.model_json_schema().get("required", [])
    assert "park_seq" not in RunSummaryOut.model_json_schema().get("required", [])
    assert "park_seq" not in RunEventsOut.model_json_schema().get("required", [])


def test_a_run_summary_omits_the_number_until_the_run_has_stopped() -> None:
    assert "park_seq" not in RunSummaryOut.of(build_run("running")).model_dump()


def test_a_run_summary_carries_the_number_once_it_has_stopped() -> None:
    out = RunSummaryOut.of(build_run("needs_you", park_seq=STOP))

    assert out.model_dump()["park_seq"] == STOP


def test_the_run_detail_summary_carries_the_number() -> None:
    out = RunDetailSummaryOut.of_run(build_run("needs_you", park_seq=STOP), admitted_signals=())

    assert out.model_dump()["park_seq"] == STOP


def event(park_seq: int) -> RunEvent:
    return RunEvent(
        run_id=build_run().id,
        status="needs_you",
        updated_at=AT,
        admitted_signals=("answer",),
        spend_usd=Decimal("0"),
        budget_usd=None,
        park_kind="blocked",
        park_path="plan",
        park_seq=park_seq,
    )


def test_the_events_read_carries_the_number_once_the_run_has_stopped() -> None:
    assert RunEventsOut.of(event(STOP), changed=False).model_dump()["park_seq"] == STOP


def test_the_events_read_omits_the_number_before_any_stop() -> None:
    assert "park_seq" not in RunEventsOut.of(event(0), changed=False).model_dump()
