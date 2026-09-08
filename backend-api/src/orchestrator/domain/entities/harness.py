"""The `harness` table: which coding-agent harnesses this instance may dispatch to (AD-10).

Seeded disabled at start-up with the three names the image installs (SPEC CAP-3); nothing
outside `application/use_cases/harness_readiness.py` (SPEC CAP-8) writes `enabled`,
`last_readiness_at`, `failing_check`, `last_readiness_run_id` or `lines`. Pre-flight's
harness line (4.3) reads `enabled` and nothing else here.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EvaluationLine(BaseModel):
    """One line `evaluate` (SPEC CAP-8) produced: one named check, and whether it passed."""

    model_config = ConfigDict(frozen=True)

    check: str
    ok: bool
    text: str


class Harness(BaseModel):
    """One harness this instance knows how to dispatch to, as it is stored."""

    model_config = ConfigDict(frozen=True)

    #: `claude`, `codex` or `local` — the three names the image installs. The primary key.
    name: str
    #: Whether a readiness run has passed. `False` until Epic 5 writes otherwise.
    enabled: bool = False
    #: When the last readiness run finished, successful or not. `None` until one has.
    last_readiness_at: datetime | None = None
    #: What the last readiness run failed on, or `None` when it passed or never ran.
    failing_check: str | None = None
    #: The version this instance's image pins for the harness (AD-16), read from Settings.
    version_pin: str
    #: The Run `evaluate` last wrote from, or `None` before one has.
    last_readiness_run_id: UUID | None = None
    #: Every line the last evaluation produced, in the order `evaluate` checked them.
    lines: tuple[EvaluationLine, ...] = ()
