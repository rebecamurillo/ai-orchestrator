"""`GET /api/v1/kit/*` — the running instance hands a project the kit that matches it.

    curl -fsSL -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" \\
      "$ORCHESTRATOR_BASE_URL/api/v1/kit/install.sh" | bash -s -- --harness claude

The script then fetches `/kit/archive` for the skills. Both are read off `KIT_DIR` by
`infrastructure/kit.py`; an instance without a kit (a source-tree run) answers 404 rather
than an empty archive, so a client never installs nothing and calls it done.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import PlainTextResponse

from orchestrator.api.errors import PROBLEM_MEDIA_TYPE, PROBLEM_SCHEMA_REF, Problem, ProblemDetail
from orchestrator.api.routers.version import instance_settings
from orchestrator.infrastructure import kit
from orchestrator.infrastructure.settings import Settings

router = APIRouter(tags=["kit"])

HTTP_NOT_FOUND = 404
SHELL_MEDIA_TYPE = "text/x-shellscript"
GZIP_MEDIA_TYPE = "application/gzip"
#: What the archive downloads as; the version is the kit's own, from its manifest.
ARCHIVE_NAME = "ai-orchestrator-kit-{version}.tar.gz"

NOT_SHIPPED = {
    "model": ProblemDetail,
    "description": "This instance ships no client kit (KIT_DIR holds no install.sh).",
    "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
}

InstanceSettings = Annotated[Settings, Depends(instance_settings)]


def _not_shipped() -> Problem:
    return Problem(
        status=HTTP_NOT_FOUND,
        title="kit not shipped",
        detail="this instance carries no client kit: KIT_DIR holds no install.sh",
    )


@router.get(
    "/kit/install.sh",
    summary="The kit installer, to pipe into bash from a project repository",
    response_class=PlainTextResponse,
    responses={
        200: {"content": {SHELL_MEDIA_TYPE: {"schema": {"type": "string"}}}},
        HTTP_NOT_FOUND: NOT_SHIPPED,
    },
)
def read_install_script(settings: InstanceSettings) -> Response:
    text = kit.install_script(settings.kit_dir)
    if text is None:
        raise _not_shipped()
    return PlainTextResponse(text, media_type=SHELL_MEDIA_TYPE)


@router.get(
    "/kit/archive",
    summary="The kit as a tar.gz — what the installer fetches when it was piped",
    response_class=Response,
    responses={
        200: {"content": {GZIP_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}}},
        HTTP_NOT_FOUND: NOT_SHIPPED,
    },
)
def read_archive(settings: InstanceSettings) -> Response:
    data = kit.archive(settings.kit_dir)
    if data is None:
        raise _not_shipped()
    name = ARCHIVE_NAME.format(version=kit.kit_version(settings.kit_dir) or "unversioned")
    return Response(
        content=data,
        media_type=GZIP_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
