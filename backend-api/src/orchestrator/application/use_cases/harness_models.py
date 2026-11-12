"""Which models a harness can use, and where the list comes from (SPEC CAP-4, C4). Pure."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal

from orchestrator.application import findings
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.gateway import GatewayModels

LOCAL = "local"
LITELLM_NOTE = "the models this instance's LiteLLM key may use"
EMPTY_NOTE = "LiteLLM lists no model for this instance's key"


@dataclass(frozen=True)
class ModelsAnswer:
    harness: str
    source: Literal["litellm", "configured", "none"]
    models: tuple[str, ...]
    note: str | None
    code: str | None
    guide: str | None


def available_models(
    harness: str,
    gateway_models: GatewayModels | None,
    local_models: tuple[str, ...],
    known: Collection[str],
) -> ModelsAnswer:
    """`GatewayUnreachable` propagates; the caller maps it."""
    if harness not in known:
        raise NotFound(f"no harness named {harness!r}")
    if harness == LOCAL:
        return ModelsAnswer(harness, "configured", local_models, None, None, None)
    if gateway_models is None:
        code = findings.REFUSAL_MODELS_UNLISTED
        note = (
            f"{harness} cannot list its models here: no LiteLLM gateway is configured; "
            "pass a model name the harness accepts"
        )
        return ModelsAnswer(harness, "none", (), note, code, findings.guide_id(code))
    listed = gateway_models.models()
    return ModelsAnswer(
        harness, "litellm", listed, LITELLM_NOTE if listed else EMPTY_NOTE, None, None
    )
