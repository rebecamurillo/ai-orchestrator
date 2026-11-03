"""Story 2-4 review: the Run read models say whether a senior session holds the Run, so a
client can withhold the controls the server would refuse (the artifact modal's Edit)."""

from __future__ import annotations

from orchestrator.api.schemas.run_views import RunDetailSummaryOut
from orchestrator.api.schemas.runs import RunSummaryOut
from orchestrator.application.rules.signals import run_admitted_signals
from orchestrator.application.use_cases.session_view import session_view
from orchestrator.application.use_cases.signals import session_ports
from tests.unit.application.session_fixtures import a_session_world
from tests.unit.application.writer_fixtures import build_run


def test_a_run_summary_omits_senior_session_until_one_is_open() -> None:
    assert "senior_session" not in RunSummaryOut.of(build_run("needs_you")).model_dump()


def test_a_run_summary_carries_senior_session_while_one_is_open() -> None:
    out = RunSummaryOut.of(build_run("needs_you", senior_session=True))

    assert out.model_dump()["senior_session"] is True


def test_the_run_detail_summary_carries_senior_session_while_one_is_open() -> None:
    out = RunDetailSummaryOut.of_run(
        build_run("needs_you", senior_session=True), admitted_signals=("cancel", "session_end")
    )

    assert out.model_dump()["senior_session"] is True


def test_the_contract_keeps_senior_session_optional() -> None:
    assert "senior_session" not in RunSummaryOut.model_json_schema().get("required", [])
    assert "default" not in RunSummaryOut.model_json_schema()["properties"]["senior_session"]


def test_a_terminal_session_offers_no_senior_session() -> None:
    session = a_session_world(terminal_session=True)
    run = session.world.stored_run()

    assert "session_start" not in run_admitted_signals(run, "agent")
    assert session_view(session_ports(session.ports), run.id).available is False
