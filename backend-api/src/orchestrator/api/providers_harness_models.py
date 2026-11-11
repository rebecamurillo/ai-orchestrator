"""The models this instance offers per harness (7.3).

A module of its own because `api/providers.py` is at its 400-line cap
(`test_source_limits.py`); it re-exports `harness_models`, keeping the function identity
`app.dependency_overrides` keys on.
"""

from __future__ import annotations

from fastapi import Request

from orchestrator.api.providers_base import SETTINGS, from_state
from orchestrator.infrastructure.harness.models import model_table


def harness_models(request: Request) -> dict[str, tuple[str, ...]]:
    """The models this instance offers per harness (7.3) — configuration, not a port.

    Its own dependency rather than a field on `HarnessPorts`: nothing here opens a
    transaction, no use case reads it, and it is composed from `Settings` on every request
    precisely so an Operator's `.env` edit reaches the New workflow's select at the next
    restart without a migration (`infrastructure/harness/models.py`).
    """
    return model_table(from_state(request, SETTINGS))
