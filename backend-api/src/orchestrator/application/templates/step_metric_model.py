"""A step-produced metric a Template catalogues: the entry, the report format, the path glob."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from orchestrator.domain.ports.catalogue import CatalogueEntry

StepMetricFormat = Literal["junit", "cobertura", "jacoco", "sarif"]

INVALID_STEP_METRIC_ID = "metric id must be step.{template}.{name}"
INVALID_STEP_METRIC_FORMAT = "invalid metric format"
INVALID_STEP_METRIC_PATH = "invalid metric path"
#: The catalogue's own reason is appended: `invalid metric entry: missing field label`.
INVALID_STEP_METRIC = "invalid metric entry"
DUPLICATE_STEP_METRIC = "duplicate metric id"


class StepMetric(BaseModel):
    """One `metrics:` entry: the catalogue entry plus where the step writes its report."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    line: int
    entry: CatalogueEntry
    format: StepMetricFormat
    path: str
