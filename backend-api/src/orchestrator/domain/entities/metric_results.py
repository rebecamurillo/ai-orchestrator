"""Calculations and the immutable result versions they write (SPEC CAP-5, RM-3).

A calculation is the one mutable record here: it moves queued → running → done | failed.
A `ResultVersion` and its `StoredMetricValue`s are written once and never changed.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

CalculationState = Literal["queued", "running", "failed", "done"]
EntryPoint = Literal["at_attempt_end", "workflow_step", "manual"]

CALCULATION_ACTIVE: frozenset[str] = frozenset({"queued", "running"})
INTERRUPTED = "interrupted"
PARTIAL_WORD = "partial"


class MetricCalculation(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    run_id: UUID
    target_n: int
    state: CalculationState
    entry_point: tuple[EntryPoint, ...]
    queued_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    output: str = ""


class ResultVersion(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    run_id: UUID
    n: int
    calculated_at: datetime
    entry_point: tuple[EntryPoint, ...]
    methods: tuple[str, ...]
    fact_set_ids: tuple[UUID, ...] = ()
    toolset_fingerprint: str | None = None


class Origin(BaseModel):
    """Where a value comes from; each field holds a value or the reason it does not apply."""

    model_config = ConfigDict(frozen=True)

    project_id: UUID
    run_id: UUID
    template_name: str
    template_version: int
    harness: str | None = None
    harness_na: str | None = None
    origin_model: str | None = None
    origin_model_na: str | None = None
    origin_repository: str | None = None
    origin_repository_na: str | None = None
    branch: str | None = None
    branch_na: str | None = None
    commit: str | None = None
    commit_na: str | None = None
    base_commit: str | None = None
    base_commit_na: str | None = None

    @model_validator(mode="after")
    def _value_or_reason(self) -> Origin:
        for name in (
            "harness",
            "origin_model",
            "origin_repository",
            "branch",
            "commit",
            "base_commit",
        ):
            if (getattr(self, name) is None) == (getattr(self, f"{name}_na") is None):
                raise ValueError(f"{name}: exactly one of the value and its reason is set")
        return self


class StoredMetricValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    version_id: UUID
    metric_id: str
    method_id: str
    scope_type: str
    scope_key: str
    scope_label: str | None = None
    role: str | None = None
    model: str | None = None
    repository: str | None = None
    attempt_n: int | None = None
    source: str | None = None
    value_num: Decimal | None = None
    unit: str = ""
    missing: str | None = None
    partial_n: int | None = None
    partial_m: int | None = None
    carried_from: int | None = None
    origin: Origin

    @model_validator(mode="after")
    def _figure_or_word(self) -> StoredMetricValue:
        if self.value_num is not None and self.missing not in (None, PARTIAL_WORD):
            raise ValueError("value_num and missing are both set")
        return self
