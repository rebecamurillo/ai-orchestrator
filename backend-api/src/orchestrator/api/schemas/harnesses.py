"""The HTTP shape of a harness row (SPEC CAP-3, AD-10)."""

from __future__ import annotations

from pydantic import BaseModel

from orchestrator.api.schemas.common import UtcTimestamp
from orchestrator.domain.entities.harness import Harness


class HarnessOut(BaseModel):
    """One row of `GET /harnesses`."""

    name: str
    enabled: bool
    last_readiness_at: UtcTimestamp | None
    failing_check: str | None
    version_pin: str

    @classmethod
    def of(cls, harness: Harness) -> HarnessOut:
        return cls(
            name=harness.name,
            enabled=harness.enabled,
            last_readiness_at=harness.last_readiness_at,
            failing_check=harness.failing_check,
            version_pin=harness.version_pin,
        )
