"""`GET /api/v1/harnesses/{name}/models` (epic 2 story 4, SPEC CAP-4).

A router of its own: `test_harnesses_router.py` pins `harnesses.router` to exactly `GET /harnesses`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    Problem,
    ProblemDetail,
)
from orchestrator.api.providers_harness_models import ModelSources, model_sources
from orchestrator.api.schemas.harnesses import ModelsOut
from orchestrator.application import findings
from orchestrator.application.use_cases.harness_models import available_models
from orchestrator.domain.entities.harness import HARNESS_NAME_PATTERN
from orchestrator.domain.ports.gateway import GatewayUnreachable

router = APIRouter(tags=["harnesses"])


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


MODELS_REFUSALS = {
    404: _refusal("No harness has that name."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("`name` does not match the shape below."),
    503: _refusal("The LiteLLM gateway is configured but its model list could not be read."),
}


@router.get(
    "/harnesses/{name}/models",
    response_model=ModelsOut,
    summary="The models a harness can use, with their source",
    responses=MODELS_REFUSALS,
)
def list_models(
    name: Annotated[str, Path(pattern=HARNESS_NAME_PATTERN)],
    sources: Annotated[ModelSources, Depends(model_sources)],
) -> ModelsOut:
    """The list names its `source`; `none` carries a `code` and `guide` and an empty list."""
    try:
        answer = available_models(name, sources.gateway_models, sources.local_models, sources.known)
    except GatewayUnreachable as error:
        code = findings.REFUSAL_MODELS_GATEWAY_UNREACHABLE
        raise Problem(
            status=503,
            title="models gateway unreachable",
            detail=findings.entry(code).message,
            code=code,
            guide=findings.guide_id(code),
        ) from error
    return ModelsOut.of(answer)
