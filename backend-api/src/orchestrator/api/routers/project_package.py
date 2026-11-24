"""`/api/v1/projects/{project_id}/package` — install, read and remove a Project's package
(SPEC CAP-3, AD-39).

Install's 422 is built here, like `templates.py::save_version`'s: the refusal names each
file and reason of one package, which the generic `DomainError` handler carries no shape for.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    Problem,
    ProblemDetail,
    finding_error,
)
from orchestrator.api.providers_packages import package_ports
from orchestrator.api.schemas.packages import PackageIn, PackageOut
from orchestrator.application.packages.declaration import PackageInvalid
from orchestrator.application.use_cases import packages as use_cases
from orchestrator.application.use_cases.packages import PackagePorts

router = APIRouter(tags=["projects"])

HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409

Ports = Annotated[PackagePorts, Depends(package_ports)]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


NOT_FOUND = _refusal("No Project or repository of it has that id, or it has no package.")
INVALID = _refusal(
    "The package or the request broke a rule; `errors[]` names each file and reason."
)
INSTALL_REFUSALS = {
    HTTP_NOT_FOUND: NOT_FOUND,
    HTTP_CONFLICT: _refusal(
        "The ref is not a branch of the remote, or another project holds a different package "
        "of the same name."
    ),
    HTTP_UNPROCESSABLE_CONTENT: INVALID,
}
READ_REFUSALS = {HTTP_NOT_FOUND: NOT_FOUND, HTTP_UNPROCESSABLE_CONTENT: INVALID}
REMOVE_REFUSALS = {
    **READ_REFUSALS,
    HTTP_CONFLICT: _refusal("Initiatives created from the package are still open."),
}


@router.put(
    "/projects/{project_id}/package",
    response_model=PackageOut,
    summary="Install a package on a Project",
    responses=INSTALL_REFUSALS,
)
def install_package(project_id: UUID, payload: PackageIn, ports: Ports) -> PackageOut:
    """Read `package.yaml` and its templates at `ref` of the hub; store them only if all pass."""
    try:
        package = use_cases.install_package(
            ports,
            project_id,
            repository_id=payload.repository_id,
            path=payload.path,
            ref=payload.ref,
        )
    except PackageInvalid as invalid:
        first = invalid.problems[0]
        raise Problem(
            status=HTTP_UNPROCESSABLE_CONTENT,
            title="invalid package",
            detail=f"{first.file}: {first.reason}",
            errors=[finding_error(path=p.file, reason=p.reason) for p in invalid.problems],
        ) from invalid
    return PackageOut.of(package, use_cases.hub_of(ports, package))


@router.get(
    "/projects/{project_id}/package",
    response_model=PackageOut,
    summary="Read a Project's installed package",
    responses=READ_REFUSALS,
)
def read_package(project_id: UUID, ports: Ports) -> PackageOut:
    """The installed record, its declaration and the hub."""
    package = use_cases.get_package(ports, project_id)
    return PackageOut.of(package, use_cases.hub_of(ports, package))


@router.delete(
    "/projects/{project_id}/package",
    status_code=204,
    response_class=Response,
    summary="Remove a Project's installed package",
    responses=REMOVE_REFUSALS,
)
def remove_package(project_id: UUID, ports: Ports) -> Response:
    """Delete the record; every stored template version stays."""
    use_cases.remove_package(ports, project_id)
    return Response(status_code=204)
