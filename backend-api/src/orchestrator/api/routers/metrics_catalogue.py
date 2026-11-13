"""`GET /api/v1/metrics/catalogue` — every metric described once, with its methods."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from orchestrator.api.schemas.common import Page
from orchestrator.api.schemas.metrics import CatalogueEntryOut
from orchestrator.domain.ports.catalogue import Catalogue
from orchestrator.infrastructure.metrics_catalogue import PackageCatalogue

router = APIRouter(tags=["metrics"])


_SHIPPED = PackageCatalogue()


def catalogue_port() -> Catalogue:
    return _SHIPPED


@router.get(
    "/metrics/catalogue",
    response_model=Page[CatalogueEntryOut],
    summary="Every metric the instance describes",
)
def read_catalogue(
    catalogue: Annotated[Catalogue, Depends(catalogue_port)],
) -> Page[CatalogueEntryOut]:
    return Page(items=[CatalogueEntryOut.from_entry(e) for e in catalogue.entries()])
