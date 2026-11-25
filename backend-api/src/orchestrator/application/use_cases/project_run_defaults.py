"""Set a Project's run defaults: what its build Run starts with (SPEC CAP-1, CAP-4).

The five fields are replaced together and a budget is never invented: `None` clears one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from orchestrator.application.use_cases import projects as project_use_cases
from orchestrator.application.use_cases.advance_retry import (
    AdvanceRetryPorts,
    retry_budget_advances,
)
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.project import AUTONOMY_MODES, ProjectView
from orchestrator.domain.errors import Invalid

HARNESS_PATTERN = re.compile(r"[a-z0-9-]+")


@dataclass(frozen=True)
class RunDefaults:
    """The five defaults, each or `None`."""

    default_budget_usd: Decimal | None
    default_harness: str | None
    default_model: str | None
    default_autonomy: str | None
    default_senior_model: str | None


def _check(defaults: RunDefaults) -> None:
    budget = defaults.default_budget_usd
    if budget is not None and budget <= 0:
        raise Invalid("default_budget_usd: must be greater than 0")
    harness = defaults.default_harness
    if harness is not None and not HARNESS_PATTERN.fullmatch(harness):
        raise Invalid("default_harness: must match ^[a-z0-9-]+$")
    for name in ("default_model", "default_senior_model"):
        value = getattr(defaults, name)
        if value is not None and not value.strip():
            raise Invalid(f"{name}: must not be empty")
    autonomy = defaults.default_autonomy
    if autonomy is not None and autonomy not in AUTONOMY_MODES:
        raise Invalid("default_autonomy: must be auto or checkpoints")


def set_run_defaults(
    ports: ProjectPorts,
    project_id: UUID,
    defaults: RunDefaults,
    retry: AdvanceRetryPorts | None = None,
) -> ProjectView:
    """Replace all five defaults of a stored Project and return its masked view.

    After the commit, `retry` wakes the advances a missing budget had blocked.
    """
    stored = project_use_cases._require(ports.projects, project_id)
    project_use_cases._refuse_builtin(stored)
    _check(defaults)
    updated = stored.model_copy(
        update={
            "default_budget_usd": defaults.default_budget_usd,
            "default_harness": defaults.default_harness,
            "default_model": defaults.default_model,
            "default_autonomy": defaults.default_autonomy,
            "default_senior_model": defaults.default_senior_model,
            "updated_at": ports.clock.now(),
        }
    )
    ports.projects.update(updated)
    ports.uow.commit()
    if retry is not None:
        retry_budget_advances(retry, project_id)
    return project_use_cases._masked(updated, ports.crypto)
