"""The HTTP shape of a harness row (SPEC CAP-3, CAP-8, AD-10).

`last_readiness_run_id` and `lines` are the fields SPEC CAP-8 adds to `GET /harnesses`'
items — this is the schema `tests/unit/test_harnesses_router.py::
test_harness_out_of_renders_every_field` and `tests/e2e/test_harnesses.py::
test_the_response_is_the_one_list_envelope` were authorised to be revised for (the
operator's own ruling on this story's anchor conflict): both stay exact closed-set
equalities, now over seven names instead of five.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from orchestrator.api.schemas.common import UtcTimestamp
from orchestrator.domain.entities.harness import EvaluationLine, Harness


class EvaluationLineOut(BaseModel):
    """One line `evaluate` produced: `{check, ok, text}`, the brief's own literal shape."""

    check: str
    ok: bool
    text: str

    @classmethod
    def of(cls, line: EvaluationLine) -> EvaluationLineOut:
        return cls(check=line.check, ok=line.ok, text=line.text)


class HarnessOut(BaseModel):
    """One row of `GET /harnesses`."""

    name: str
    enabled: bool
    last_readiness_at: UtcTimestamp | None
    failing_check: str | None
    version_pin: str
    #: Defaulted, not merely nullable: the generated client type marks both optional, so
    #: `web-client/tests/unit/harness-list.test.ts`'s and `newwf-state.test.ts`'s existing
    #: fixtures — frozen, and predating this story — keep compiling unchanged. `model_dump()`
    #: still renders both keys always; only the OpenAPI `required` list changes.
    last_readiness_run_id: UUID | None = None
    lines: list[EvaluationLineOut] = Field(default_factory=list)

    @classmethod
    def of(cls, harness: Harness) -> HarnessOut:
        return cls(
            name=harness.name,
            enabled=harness.enabled,
            last_readiness_at=harness.last_readiness_at,
            failing_check=harness.failing_check,
            version_pin=harness.version_pin,
            last_readiness_run_id=harness.last_readiness_run_id,
            lines=[EvaluationLineOut.of(line) for line in harness.lines],
        )
