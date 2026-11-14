"""Spend this month, the Runs of a project, and the comparison with its export files
(epic 4 story 1; ARCHITECTURE §6.1)."""

from __future__ import annotations

import csv
import io
import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers_metrics import metrics_compare_ports, metrics_home_ports
from orchestrator.api.schemas.common import Page
from orchestrator.api.schemas.metrics_compare import (
    CompareExportOut,
    CompareOut,
    MetricsRunOut,
    ProjectSpendOut,
)
from orchestrator.application.metrics.export_rows import EXPORT_COLUMNS
from orchestrator.application.use_cases.metrics_compare import (
    CompareQuery,
    MetricsComparePorts,
    compare_runs,
    export_rows,
    parse_runs,
    parse_versions,
)
from orchestrator.application.use_cases.metrics_spend import (
    MetricsHomePorts,
    project_runs,
    spend_this_month,
)

router = APIRouter(tags=["metrics"])

HomePorts = Annotated[MetricsHomePorts, Depends(metrics_home_ports)]
ComparePorts = Annotated[MetricsComparePorts, Depends(metrics_compare_ports)]
RunsQuery = Annotated[str, Query(description="Run ids, comma separated, in column order.")]
VersionsQuery = Annotated[str, Query(description="`{run}:{n}` pairs, comma separated.")]
BlindQuery = Annotated[bool, Query(description="Hide labels, template and model names.")]
UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


INVALID = _refusal("A query value is not valid, or the selection is not comparable.")
COMPARE_REFUSALS = {
    404: _refusal("No Run has that id, or a Run has no such version."),
    HTTP_UNPROCESSABLE_CONTENT: INVALID,
}
PROJECT_REFUSALS = {
    404: _refusal("No project has that id."),
    HTTP_UNPROCESSABLE_CONTENT: INVALID,
}


def _query(runs: str, v: str, blind: bool) -> CompareQuery:
    return CompareQuery(parse_runs(runs), parse_versions(v), blind)


def _disposition(project: str, ports: MetricsComparePorts, extension: str) -> str:
    day = ports.clock.now().strftime("%Y-%m-%d")
    name = UNSAFE.sub("-", project).strip("-") or "project"
    return f'attachment; filename="{name}-compare-{day}.{extension}"'


@router.get(
    "/metrics/spend",
    response_model=Page[ProjectSpendOut],
    summary="Spend this month per project, both figures, cancelled Runs apart",
)
def read_spend(ports: HomePorts) -> Page[ProjectSpendOut]:
    return Page[ProjectSpendOut](
        items=[ProjectSpendOut.of(item) for item in spend_this_month(ports)], next_cursor=None
    )


@router.get(
    "/metrics/runs",
    response_model=Page[MetricsRunOut],
    summary="A project's Runs, newest first, with what the Metrics table shows",
    responses=PROJECT_REFUSALS,
)
def read_runs(ports: HomePorts, project: UUID) -> Page[MetricsRunOut]:
    return Page[MetricsRunOut](
        items=[MetricsRunOut.of(item) for item in project_runs(ports, project)], next_cursor=None
    )


@router.get(
    "/metrics/compare",
    response_model=CompareOut,
    summary="Selected Runs of one project, side by side",
    responses=COMPARE_REFUSALS,
)
def read_compare(
    ports: ComparePorts, runs: RunsQuery, v: VersionsQuery = "", blind: BlindQuery = False
) -> CompareOut:
    return CompareOut.of(compare_runs(ports, _query(runs, v, blind)))


@router.get(
    "/metrics/compare.csv",
    summary="The comparison as one CSV row per stored value",
    responses={
        **COMPARE_REFUSALS,
        200: {"content": {"text/csv": {"schema": {"type": "string"}}}},
    },
    response_class=Response,
)
def export_csv(
    ports: ComparePorts, runs: RunsQuery, v: VersionsQuery = "", blind: BlindQuery = False
) -> Response:
    result = export_rows(ports, _query(runs, v, blind))
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)
    for row in result.rows:
        writer.writerow([getattr(row, column) for column in EXPORT_COLUMNS])
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": _disposition(result.project_name, ports, "csv")},
    )


@router.get(
    "/metrics/compare.json",
    response_model=CompareExportOut,
    summary="The comparison as JSON: the runs, the same rows, the catalogue once",
    responses=COMPARE_REFUSALS,
)
def export_json(
    ports: ComparePorts,
    response: Response,
    runs: RunsQuery,
    v: VersionsQuery = "",
    blind: BlindQuery = False,
) -> CompareExportOut:
    result = export_rows(ports, _query(runs, v, blind))
    response.headers["Content-Disposition"] = _disposition(result.project_name, ports, "json")
    return CompareExportOut.of(result)
