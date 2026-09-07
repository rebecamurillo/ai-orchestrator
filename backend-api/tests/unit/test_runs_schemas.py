"""The HTTP shape of `POST /runs` / `GET /runs/{id}` (`api/schemas/runs.py`, SPEC CAP-4).

The router tests (`test_run_router.py`) prove these render correctly through a real
request; this module is where the conversions themselves — `RunIn.as_request()`,
`RunSummaryOut.of()`, `CreateRunOut.of()`, `plan_error_problems()` — are exercised directly,
the way `test_templates_schemas.py` does for `api/schemas/templates.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from orchestrator.api.schemas.runs import CreateRunOut, RunIn, RunSummaryOut, plan_error_problems
from orchestrator.application.templates.plan_model import PlanError
from orchestrator.application.use_cases.create_run import CreateRunRequest, CreateRunResult
from orchestrator.domain.entities.run import Run

AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
RUN_ID = UUID("01960000-0000-7000-9000-000000000001")
PROJECT_ID = UUID("01960000-0000-7000-9000-000000000002")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-000000000003")


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": RUN_ID,
        "project_id": PROJECT_ID,
        "repository_id": REPOSITORY_ID,
        "template_name": "repo-init",
        "template_version": 1,
        "status": "queued",
        "inputs": {"base_branch": "main"},
        "plan_ref": "abc123",
        "budget_usd": Decimal("10"),
        "spend_usd": Decimal("0"),
        "created_at": AT,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


# ── RunIn.as_request() ───────────────────────────────────────────────────────────────────


def test_run_in_as_request_carries_every_field() -> None:
    payload = RunIn(
        template_name="repo-init",
        template_version=1,
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        base_branch="main",
        budget_usd=Decimal("12.5"),
        harness="claude",
        manual_estimate_h=Decimal("2"),
    )

    request = payload.as_request()

    assert isinstance(request, CreateRunRequest)
    assert request.template_name == "repo-init"
    assert request.project_id == PROJECT_ID
    assert request.repository_id == REPOSITORY_ID
    assert request.budget_usd == Decimal("12.5")
    assert request.harness == "claude"
    assert request.manual_estimate_h == Decimal("2")
    assert request.re_review_done is False


def test_run_in_refuses_a_zero_budget() -> None:
    with pytest.raises(ValidationError):
        RunIn(
            template_name="repo-init",
            template_version=1,
            project_id=PROJECT_ID,
            repository_id=REPOSITORY_ID,
            base_branch="main",
            budget_usd=Decimal("0"),
        )


def test_run_in_refuses_a_budget_too_large_to_quantize_rather_than_500ing() -> None:
    """The schemathesis gate's own find (4.4): a finite but enormous magnitude used to
    raise an uncaught `decimal.InvalidOperation` out of `MoneyStr` — fixed in
    `api/schemas/common.py::_as_money`, proven here through `budget_usd`, its first
    consumer."""
    with pytest.raises(ValidationError):
        RunIn(
            template_name="repo-init",
            template_version=1,
            project_id=PROJECT_ID,
            repository_id=REPOSITORY_ID,
            base_branch="main",
            budget_usd=Decimal("1e284"),
        )


# ── RunSummaryOut.of() ───────────────────────────────────────────────────────────────────


def test_run_summary_out_renders_the_minimal_fields() -> None:
    out = RunSummaryOut.of(a_run())

    assert out.id == RUN_ID
    assert out.status == "queued"
    assert out.template == "repo-init"
    assert out.version == 1
    assert out.project == PROJECT_ID
    assert out.repository == REPOSITORY_ID
    assert out.branch == "main"
    assert out.plan_ref == "abc123"


def test_run_summary_out_renders_money_as_a_decimal_string() -> None:
    dumped = RunSummaryOut.of(a_run(budget_usd=Decimal("10"))).model_dump(mode="json")

    assert dumped["budget_usd"] == "10.000000"
    assert dumped["spend_usd"] == "0.000000"


def test_run_summary_out_falls_back_to_an_empty_branch() -> None:
    out = RunSummaryOut.of(a_run(inputs={}))

    assert out.branch == ""


# ── CreateRunOut.of() ────────────────────────────────────────────────────────────────────


def test_create_run_out_of_a_result() -> None:
    result = CreateRunResult(run=a_run(), starts_now=True, waiting="starts immediately")

    out = CreateRunOut.of(result)

    assert out.run.id == RUN_ID
    assert out.starts_now is True
    assert out.waiting == "starts immediately"


# ── plan_error_problems() ────────────────────────────────────────────────────────────────


ERROR_LINE = 3


def test_plan_error_problems_names_template_version_line_item_reason() -> None:
    error = PlanError(
        reason="list file not found", template="epic", version=1, line=ERROR_LINE, item="x"
    )

    (problem,) = plan_error_problems(error)

    assert problem.template == "epic"
    assert problem.version == "1"
    assert problem.line == ERROR_LINE
    assert problem.path == "x"
    assert problem.reason == "list file not found"


def test_plan_error_problems_tolerates_no_template() -> None:
    error = PlanError(reason="base branch not found", item="main")

    (problem,) = plan_error_problems(error)

    assert problem.template is None
    assert problem.version is None
    assert problem.path == "main"
