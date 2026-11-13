"""A Run's metrics: stored versions, the values so far, and the calculation that makes one
(epic 2 story 5; SPEC CAP-5)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers_metrics import calculate_ports, metrics_query_ports
from orchestrator.api.schemas.common import Page
from orchestrator.api.schemas.metric_results import (
    CalculationOut,
    ResultVersionOut,
    RunMetricsOut,
)
from orchestrator.application.use_cases.metric_calculations import (
    CalculatePorts,
    request_calculation,
)
from orchestrator.application.use_cases.metrics_read import (
    MetricsQueryPorts,
    calculation_for,
    list_versions,
    run_metrics,
)

router = APIRouter(tags=["metrics"])

QueryPorts = Annotated[MetricsQueryPorts, Depends(metrics_query_ports)]
WritePorts = Annotated[CalculatePorts, Depends(calculate_ports)]
HTTP_ACCEPTED = 202


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


INVALID = _refusal("A path or query value is not valid.")
NOT_FOUND = {
    404: _refusal("No such Run, version or calculation."),
    HTTP_UNPROCESSABLE_CONTENT: INVALID,
}
CALCULATE_REFUSALS = {
    404: _refusal("No Run has that id."),
    HTTP_UNPROCESSABLE_CONTENT: INVALID,
    409: _refusal("The Run has not ended, or a calculation of it is queued or running."),
}


@router.get(
    "/runs/{run_id}/metrics",
    response_model=RunMetricsOut,
    summary="A Run's metric values: a stored version, or the values so far on a live Run",
    responses=NOT_FOUND,
)
def read_metrics(
    run_id: UUID, ports: QueryPorts, v: Annotated[int | None, Query(ge=1)] = None
) -> RunMetricsOut:
    return RunMetricsOut.of(run_metrics(ports, run_id, v))


@router.get(
    "/runs/{run_id}/metrics/versions",
    response_model=Page[ResultVersionOut],
    summary="The result versions of a Run, with the methods each changed",
    responses=NOT_FOUND,
)
def read_versions(run_id: UUID, ports: QueryPorts) -> Page[ResultVersionOut]:
    return Page[ResultVersionOut](
        items=[ResultVersionOut.of(view) for view in list_versions(ports, run_id)], next_cursor=None
    )


@router.post(
    "/runs/{run_id}/metrics/calculate",
    response_model=CalculationOut,
    status_code=HTTP_ACCEPTED,
    summary="Calculate a new result version of an ended Run",
    responses=CALCULATE_REFUSALS,
)
def calculate(run_id: UUID, ports: WritePorts) -> CalculationOut:
    return CalculationOut.of(request_calculation(ports, run_id))


@router.get(
    "/runs/{run_id}/metrics/calculations/{n}",
    response_model=CalculationOut,
    summary="The state and output of the calculation that makes version n",
    responses=NOT_FOUND,
)
def read_calculation(
    run_id: UUID, n: Annotated[int, Path(ge=1)], ports: QueryPorts
) -> CalculationOut:
    return CalculationOut.of(calculation_for(ports, run_id, n))
