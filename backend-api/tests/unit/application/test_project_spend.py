"""`project_metrics` (story 8-6): per-project monthly spend, provisional flag, needs_you
count, and failed-recent count — all derived from one `runs.list(project_id=...)` call.

Tests are written first (TDD): all should fail until `project_spend.py` is created.
Uses `FakeRunRepository` from `tests/unit/fakes/runs.py` — no new doubles for an existing
port (AGENTS.md hard rule 6).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from orchestrator.application.use_cases.project_spend import project_metrics
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from tests.unit.fakes.runs import FakeRunRepository

PROJECT_ID = new_id()
OTHER_PROJECT_ID = new_id()
REPOSITORY_ID = new_id()

# A reference "now" that is the 15th of the month so boundary tests are unambiguous.
NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)
THIS_MONTH_START = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
LAST_MONTH = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)

TWO_NEEDS_YOU = 2


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT_ID,
        "repository_id": REPOSITORY_ID,
        "template_name": "dev",
        "template_version": 1,
        "status": "done",
        "budget_usd": Decimal("10"),
        "spend_usd": Decimal("0"),
        "spend_provisional": False,
        "created_at": NOW,
        "started_at": NOW,
        "ended_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


# ── monthly spend ─────────────────────────────────────────────────────────────


def test_monthly_spend_sums_only_runs_started_this_month() -> None:
    runs = FakeRunRepository()
    runs.add(a_run(spend_usd=Decimal("12.30"), started_at=NOW))
    runs.add(a_run(spend_usd=Decimal("40.00"), started_at=LAST_MONTH))

    m = project_metrics(runs, PROJECT_ID, NOW)

    assert m.monthly_spend_usd == "12.30"


def test_monthly_spend_is_zero_when_no_runs_started_this_month() -> None:
    runs = FakeRunRepository()
    runs.add(a_run(spend_usd=Decimal("40.00"), started_at=LAST_MONTH))

    m = project_metrics(runs, PROJECT_ID, NOW)

    assert m.monthly_spend_usd == "0.00"


def test_run_with_started_at_none_is_excluded_from_monthly_sum() -> None:
    runs = FakeRunRepository()
    runs.add(a_run(spend_usd=Decimal("99.00"), started_at=None))

    m = project_metrics(runs, PROJECT_ID, NOW)

    assert m.monthly_spend_usd == "0.00"


def test_monthly_spend_two_decimal_places_exact() -> None:
    """Format is f"{total:.2f}" — 2 decimal places, no rounding artefact."""
    runs = FakeRunRepository()
    runs.add(a_run(spend_usd=Decimal("5.40"), started_at=NOW))

    m = project_metrics(runs, PROJECT_ID, NOW)

    assert m.monthly_spend_usd == "5.40"


# ── provisional flag ──────────────────────────────────────────────────────────


def test_monthly_spend_provisional_false_when_no_provisional_runs() -> None:
    runs = FakeRunRepository()
    runs.add(a_run(spend_usd=Decimal("5.00"), spend_provisional=False, started_at=NOW))

    m = project_metrics(runs, PROJECT_ID, NOW)

    assert m.monthly_spend_provisional is False


def test_monthly_spend_provisional_true_when_any_this_month_run_is_provisional() -> None:
    runs = FakeRunRepository()
    runs.add(a_run(spend_usd=Decimal("5.00"), spend_provisional=True, started_at=NOW))
    runs.add(a_run(spend_usd=Decimal("3.00"), spend_provisional=False, started_at=NOW))

    m = project_metrics(runs, PROJECT_ID, NOW)

    assert m.monthly_spend_provisional is True


def test_provisional_flag_on_last_month_run_does_not_affect_current_month() -> None:
    runs = FakeRunRepository()
    runs.add(a_run(spend_usd=Decimal("5.00"), spend_provisional=True, started_at=LAST_MONTH))

    m = project_metrics(runs, PROJECT_ID, NOW)

    assert m.monthly_spend_provisional is False


# ── needs_you count ───────────────────────────────────────────────────────────


def test_needs_you_count_all_parked_runs_regardless_of_time() -> None:
    runs = FakeRunRepository()
    runs.add(a_run(status="needs_you", started_at=LAST_MONTH))
    runs.add(a_run(status="needs_you", started_at=NOW))
    runs.add(a_run(status="done", started_at=NOW))

    m = project_metrics(runs, PROJECT_ID, NOW)

    assert m.needs_you_count == TWO_NEEDS_YOU


def test_needs_you_count_zero_when_none_parked() -> None:
    runs = FakeRunRepository()
    runs.add(a_run(status="done"))

    m = project_metrics(runs, PROJECT_ID, NOW)

    assert m.needs_you_count == 0


# ── failed_recent count ───────────────────────────────────────────────────────


def test_failed_recent_uses_ended_at_within_7_days() -> None:
    recent_ended = NOW - timedelta(days=3)
    runs = FakeRunRepository()
    runs.add(
        a_run(status="failed", ended_at=recent_ended, created_at=LAST_MONTH, started_at=LAST_MONTH)
    )

    m = project_metrics(runs, PROJECT_ID, NOW)

    assert m.failed_recent_count == 1


def test_failed_recent_uses_created_at_fallback_when_ended_at_none() -> None:
    """A run that never ended uses created_at as the timestamp for the 7-day window."""
    recent_created = NOW - timedelta(days=2)
    runs = FakeRunRepository()
    runs.add(
        a_run(status="failed", ended_at=None, created_at=recent_created, started_at=recent_created)
    )

    m = project_metrics(runs, PROJECT_ID, NOW)

    assert m.failed_recent_count == 1


def test_failed_run_older_than_7_days_excluded() -> None:
    old_ended = NOW - timedelta(days=8)
    runs = FakeRunRepository()
    runs.add(a_run(status="failed", ended_at=old_ended, created_at=old_ended, started_at=old_ended))

    m = project_metrics(runs, PROJECT_ID, NOW)

    assert m.failed_recent_count == 0


def test_failed_recent_count_zero_when_no_failed_runs() -> None:
    runs = FakeRunRepository()
    runs.add(a_run(status="done"))

    m = project_metrics(runs, PROJECT_ID, NOW)

    assert m.failed_recent_count == 0


# ── runs=None short-circuit ───────────────────────────────────────────────────


def test_returns_zeros_when_runs_is_none() -> None:
    m = project_metrics(None, PROJECT_ID, NOW)

    assert m.monthly_spend_usd == "0.00"
    assert m.monthly_spend_provisional is False
    assert m.needs_you_count == 0
    assert m.failed_recent_count == 0


# ── project isolation ─────────────────────────────────────────────────────────


def test_metrics_only_count_runs_for_the_given_project_id() -> None:
    runs = FakeRunRepository()
    runs.add(a_run(project_id=PROJECT_ID, spend_usd=Decimal("5.00"), started_at=NOW, status="done"))
    runs.add(
        a_run(
            project_id=OTHER_PROJECT_ID,
            spend_usd=Decimal("99.00"),
            started_at=NOW,
            status="needs_you",
        )
    )

    m = project_metrics(runs, PROJECT_ID, NOW)

    assert m.monthly_spend_usd == "5.00"
    assert m.needs_you_count == 0
