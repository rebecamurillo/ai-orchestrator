"""`/api/v1/templates` — reading, validating, and extending Template Versions (SPEC CAP-3).

Every path here publishes a `GET` except `POST /templates/reload` (story 5, 2026-11-06, D3,
the one POST with no sibling): `test_bearer_auth.py` indexes every published path's
`get` operation (see `api/routers/clone_check.py`'s docstring), so the two POST-only actions
each carry a real, read-only sibling at the same path rather than a placeholder — `GET
.../versions` lists the version numbers a Template holds, and `GET .../validate` re-runs
`validate()` over the latest stored version, the one diagnostic a client can ask for without
first finding a version number or supplying a body.

`save_version`'s 422 is the one place a router in this system builds a `Problem` itself
rather than letting a raised `DomainError` become one: the validator's errors are structured
(`template`, `version`, `line`, `reason`), and `api/errors.py`'s generic `DomainError`
handler carries no such shape. The two other save refusals — a `name` or `version` that
does not match the path — stay plain `Invalid`, mapped the usual way. The folder refusal
(`refuse_if_in_folder`, AD-34) is built here too: it is a decision about this request, taken
before anything is validated or stored.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi import status as http_status

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    Problem,
    ProblemDetail,
)
from orchestrator.api.providers import template_ports
from orchestrator.api.schemas.common import MAX_VERSION, Page
from orchestrator.api.schemas.templates import (
    SaveVersionIn,
    TemplateReloadOut,
    TemplateSummaryOut,
    TemplateVersionOut,
    ValidateIn,
    ValidateOut,
    as_problem_errors,
)
from orchestrator.application import findings
from orchestrator.application.use_cases import template_reload
from orchestrator.application.use_cases import templates as use_cases
from orchestrator.application.use_cases.templates import TemplatePorts, TemplateValidationFailed

router = APIRouter(tags=["templates"])

HTTP_NOT_FOUND = 404


def _refusal(description: str) -> dict[str, object]:
    """One declared error response, in the shape this API actually sends."""
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


NOT_FOUND_RESPONSE = _refusal("No Template has that name, or no version has that number.")
VALIDATION_RESPONSE = _refusal(
    "The posted YAML failed validation; `errors[]` names each problem by line."
)

# Every operation below declares its own 422, whatever its actual path or body shape: left
# undeclared, FastAPI publishes its own `HTTPValidationError` schema instead, and
# `test_projects_router.py::test_every_published_refusal_is_the_problem_document_this_api_sends`
# checks — for the whole document, not just its own paths — that this API never does.
READ_REFUSALS = {
    HTTP_NOT_FOUND: NOT_FOUND_RESPONSE,
    HTTP_UNPROCESSABLE_CONTENT: VALIDATION_RESPONSE,
}
SAVE_REFUSALS = {
    HTTP_NOT_FOUND: NOT_FOUND_RESPONSE,
    http_status.HTTP_409_CONFLICT: _refusal(
        "`refuse_if_in_folder` was set and the operator's template folder holds this name "
        "(`refusal-template-in-folder`), or a concurrent save took this version number "
        "(`conflict`); nothing is stored."
    ),
    HTTP_UNPROCESSABLE_CONTENT: VALIDATION_RESPONSE,
}
CONFLICT_RESPONSE = _refusal(
    "The template folder is not configured, or its path does not exist, or a concurrent "
    "save took a version number; nothing is stored."
)
VALIDATE_TEXT_REFUSALS = {HTTP_UNPROCESSABLE_CONTENT: VALIDATION_RESPONSE}

Ports = Annotated[TemplatePorts, Depends(template_ports)]


@router.get("/templates", response_model=Page[TemplateSummaryOut], summary="List every Template")
def list_templates(ports: Ports) -> Page[TemplateSummaryOut]:
    """Every stored Template name, its versions, and its latest description."""
    stems = use_cases.folder_stems(ports)
    items = [
        TemplateSummaryOut.of(summary, in_folder=summary.name in stems)
        for summary in use_cases.list_templates(ports)
    ]
    return Page[TemplateSummaryOut](items=items, next_cursor=None)


@router.post(
    "/templates/reload",
    response_model=TemplateReloadOut,
    summary="Reload the operator's template folder",
    responses={http_status.HTTP_409_CONFLICT: CONFLICT_RESPONSE},
)
def reload_folder(ports: Ports) -> TemplateReloadOut:
    """Re-reads the folder and stores each changed, valid file as the next version."""
    return TemplateReloadOut.of(template_reload.reload_folder(ports))


@router.get(
    "/templates/{name}/versions",
    response_model=Page[int],
    summary="List a Template's stored version numbers",
    responses=READ_REFUSALS,
)
def list_versions(name: str, ports: Ports) -> Page[int]:
    """Ascending version numbers. An unknown name is a 404, not an empty page."""
    return Page[int](items=use_cases.list_versions(ports, name), next_cursor=None)


def _held_in_folder(name: str, ports: TemplatePorts) -> Problem:
    path = ports.folders.operator().path if ports.folders is not None else ""
    return Problem(
        status=http_status.HTTP_409_CONFLICT,
        title="template held in the operator folder",
        detail=(
            f"{name}.yaml is in the operator template folder {path}; have the file edited on "
            "the host, then call reload_templates."
        ),
        code=findings.REFUSAL_TEMPLATE_IN_FOLDER,
        guide=findings.guide_id(findings.REFUSAL_TEMPLATE_IN_FOLDER),
    )


@router.post(
    "/templates/{name}/versions",
    response_model=TemplateVersionOut,
    status_code=http_status.HTTP_201_CREATED,
    summary="Save the next Template Version",
    responses=SAVE_REFUSALS,
)
def save_version(name: str, payload: SaveVersionIn, ports: Ports) -> TemplateVersionOut:
    """`version` must be `max(existing) + 1`; a saved version can never be changed (AD-15)."""
    if payload.refuse_if_in_folder is True and name in use_cases.folder_stems(ports):
        raise _held_in_folder(name, ports)
    try:
        saved = use_cases.save_version(ports, name, payload.yaml)
    except TemplateValidationFailed as failure:
        first = failure.errors[0]
        raise Problem(
            status=HTTP_UNPROCESSABLE_CONTENT,
            title="invalid template",
            detail=f"line {first.line}: {first.reason}",
            errors=as_problem_errors(failure.errors),
        ) from failure
    stems = use_cases.folder_stems(ports)
    return TemplateVersionOut.of(
        use_cases.get_version(ports, name, saved.version), in_folder=name in stems
    )


@router.get(
    "/templates/{name}/validate",
    response_model=ValidateOut,
    summary="Validate the latest stored Version",
    responses=READ_REFUSALS,
)
def validate_latest(name: str, ports: Ports) -> ValidateOut:
    """Re-runs `validate()` over the latest stored version. Never writes anything."""
    return ValidateOut.of(use_cases.validate_latest(ports, name))


@router.post(
    "/templates/{name}/validate",
    response_model=ValidateOut,
    summary="Validate posted YAML without storing it",
    responses=VALIDATE_TEXT_REFUSALS,
)
def validate_text(name: str, payload: ValidateIn, ports: Ports) -> ValidateOut:
    """A validation problem is data in this response, never a 422 (NFR-2)."""
    return ValidateOut.of(use_cases.validate_text(ports, payload.yaml))


# Registered last: Starlette matches routes in registration order, and `{version}` would
# otherwise swallow the literal `versions` and `validate` segments above as an int it then
# fails to parse — a 422, not the 404 or 200 those two literal paths mean to answer.
@router.get(
    "/templates/{name}/{version}",
    response_model=TemplateVersionOut,
    summary="Read one Template Version",
    responses=READ_REFUSALS,
)
def get_version(
    name: str, version: Annotated[int, Path(gt=0, le=MAX_VERSION)], ports: Ports
) -> TemplateVersionOut:
    """`calls`, `called_by`, `inputs` and `pinned_by` (4.4) alongside the stored text."""
    stems = use_cases.folder_stems(ports)
    return TemplateVersionOut.of(
        use_cases.get_version(ports, name, version), in_folder=name in stems
    )
