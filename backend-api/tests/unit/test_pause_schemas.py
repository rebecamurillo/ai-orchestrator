"""Story 2-1: `pause_requested` at the HTTP shape, the column that stores it, and its migration."""

from __future__ import annotations

import ast
from pathlib import Path

from orchestrator.api.schemas.run_views import RunDetailSummaryOut
from orchestrator.api.schemas.runs import RunSummaryOut
from orchestrator.api.schemas.signals import SignalIn
from orchestrator.infrastructure.db.models.run import RunRow
from orchestrator.infrastructure.db.repositories.runs import row_values, to_entity
from tests.unit.application.writer_fixtures import build_run

STOP = 2
MIGRATION = Path(__file__).parents[2] / "alembic" / "versions" / "0025_run_pause_requested.py"


def test_a_pause_signal_body_is_accepted() -> None:
    assert SignalIn(kind="pause").as_signal().kind == "pause"


def test_a_run_summary_omits_the_request_until_one_is_made() -> None:
    assert "pause_requested" not in RunSummaryOut.of(build_run("running")).model_dump()


def test_a_run_summary_carries_the_request_while_it_stands() -> None:
    out = RunSummaryOut.of(build_run("running", pause_requested=True))

    assert out.model_dump()["pause_requested"] is True
    assert out.model_dump_json().count('"pause_requested":true') == 1


def test_the_run_detail_summary_carries_it_too() -> None:
    out = RunDetailSummaryOut.of_run(
        build_run("running", pause_requested=True), admitted_signals=("cancel",)
    )

    assert out.model_dump()["pause_requested"] is True


def test_a_summary_with_a_stop_and_no_request_keeps_the_stop_number() -> None:
    dumped = RunSummaryOut.of(build_run("needs_you", park_seq=STOP)).model_dump()

    assert dumped["park_seq"] == STOP
    assert "pause_requested" not in dumped


def test_the_contract_keeps_the_field_optional() -> None:
    assert "pause_requested" not in RunSummaryOut.model_json_schema().get("required", [])


def test_the_run_row_round_trips_the_request() -> None:
    run = build_run("running", pause_requested=True)

    stored = RunRow(**row_values(run))

    assert to_entity(stored).pause_requested is True


def test_a_row_the_database_has_not_filled_yet_reads_false() -> None:
    stored = RunRow(**row_values(build_run("running")))
    stored.pause_requested = None  # type: ignore[assignment]

    assert to_entity(stored).pause_requested is False


def test_migration_0025_adds_the_column_with_a_false_default() -> None:
    source = MIGRATION.read_text()
    tree = ast.parse(source)
    assigned = {
        node.target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value
    }

    assert assigned["revision"] == "0025_run_pause_requested"
    assert assigned["down_revision"] == "0024_step_run_consults"
    assert "pause_requested" in source
    assert 'server_default=sa.text("false")' in source
    assert "nullable=False" in source
