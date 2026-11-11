"""`harness_models` lives in `providers_harness_models` and `api/providers.py` re-exports it,
keeping the identity `dependency_overrides` keys on (story 2, orchestrator-deploy-folder
epic 1, 2026-11-11)."""

from __future__ import annotations

from orchestrator.api import providers, providers_harness_models


def test_the_provider_module_re_exports_the_same_function() -> None:
    assert providers.harness_models is providers_harness_models.harness_models
