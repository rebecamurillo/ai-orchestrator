"""The gateway reads of a Run beside the harness figure (epic 2 story 6; SPEC CAP-6)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from orchestrator.api.providers_metrics import metrics_query_ports
from orchestrator.api.routers.run_metrics import NOT_FOUND
from orchestrator.api.schemas.common import Page
from orchestrator.api.schemas.metric_results import AttemptGatewayReadsOut
from orchestrator.application.use_cases.gateway_comparison import gateway_comparison
from orchestrator.application.use_cases.metrics_read import MetricsQueryPorts

router = APIRouter(tags=["metrics"])

QueryPorts = Annotated[MetricsQueryPorts, Depends(metrics_query_ports)]


@router.get(
    "/runs/{run_id}/metrics/gateway-reads",
    response_model=Page[AttemptGatewayReadsOut],
    summary="Per attempt, the gateway reads beside the harness figure",
    responses=NOT_FOUND,
)
def read_gateway_reads(run_id: UUID, ports: QueryPorts) -> Page[AttemptGatewayReadsOut]:
    return Page[AttemptGatewayReadsOut](
        items=[AttemptGatewayReadsOut.of(i) for i in gateway_comparison(ports.read, run_id)],
        next_cursor=None,
    )
