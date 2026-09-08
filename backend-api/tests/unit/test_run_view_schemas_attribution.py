"""`AttributionOut`, `AlertOut.attribution` and `LatestAttemptOut.cost_provisional` (5.10,
SPEC CAP-10) — does not touch the frozen `test_run_view_schemas.py`.

Also proves the `api/schemas/board_view.py` split (5.10, line count alone): `BoardOut`/
`CardOut`/`ProgressOut`/`BoardColumnsOut`/`BoardCountsOut` are the *same* classes whether
imported off `run_views` (the re-export) or `board_view` (where they now live) — the contract
`api/routers/run.py` and the frozen `test_run_view_schemas.py` both rely on.
"""

from __future__ import annotations

from datetime import UTC, datetime

from orchestrator.api.schemas import board_view as board_view_schemas
from orchestrator.api.schemas.run_views import AlertOut, AttributionOut, LatestAttemptOut
from orchestrator.api.schemas.run_views import BoardColumnsOut as ReexportedBoardColumnsOut
from orchestrator.api.schemas.run_views import BoardCountsOut as ReexportedBoardCountsOut
from orchestrator.api.schemas.run_views import BoardOut as ReexportedBoardOut
from orchestrator.api.schemas.run_views import CardOut as ReexportedCardOut
from orchestrator.api.schemas.run_views import ProgressOut as ReexportedProgressOut
from orchestrator.application.use_cases.run_view_types import Alert, Attribution, LatestAttempt

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_re_exported_board_classes_are_the_ones_board_view_defines() -> None:
    assert ReexportedBoardOut is board_view_schemas.BoardOut
    assert ReexportedCardOut is board_view_schemas.CardOut
    assert ReexportedProgressOut is board_view_schemas.ProgressOut
    assert ReexportedBoardColumnsOut is board_view_schemas.BoardColumnsOut
    assert ReexportedBoardCountsOut is board_view_schemas.BoardCountsOut


def test_an_attribution_carries_every_field() -> None:
    out = AttributionOut.of(Attribution(harness="claude", model="claude-opus-4", ended_at=NOW))

    assert out.harness == "claude"
    assert out.model == "claude-opus-4"
    assert out.ended_at == NOW


def test_an_alert_with_no_attribution_stays_none() -> None:
    out = AlertOut.of(Alert(token="BLK", reason="plan stale: stories.yaml", park_kind="plan_stale"))

    assert out.attribution is None


def test_an_alert_projects_its_attribution() -> None:
    attribution = Attribution(harness="claude", model="claude-opus-4", ended_at=NOW)
    alert = Alert(
        token="BLK", reason="## Auto Run Result", park_kind="blocked", attribution=attribution
    )

    out = AlertOut.of(alert)

    assert out.attribution is not None
    assert out.attribution.harness == "claude"
    assert out.attribution.model == "claude-opus-4"
    assert out.attribution.ended_at == NOW


def test_a_latest_attempt_projects_cost_provisional() -> None:
    latest = LatestAttempt(
        n=1,
        started_at=None,
        ended_at=None,
        seconds=None,
        harness="claude",
        model="claude-opus-4",
        exit_code=None,
        cost_usd=None,
        log_tail=[],
        cost_provisional=True,
    )

    out = LatestAttemptOut.of(latest)

    assert out.cost_provisional is True
