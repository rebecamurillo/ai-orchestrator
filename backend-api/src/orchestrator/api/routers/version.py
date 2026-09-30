"""`GET /api/v1/version` — what this instance is, for the handshake a client kit performs.

A project's installed kit records the version it came from; the skill's first call is this
route, and a mismatch stops it before it uses an endpoint this instance does not have
(plan agent-delivery-kit §3). The numbers come from two places only: the distribution's
own version (the root `VERSION`, which `scripts/check_version.py` holds every manifest to)
and the pinned tool versions `Settings` already carries (AD-16).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as metadata_version
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

import orchestrator
from orchestrator.api.providers_base import SETTINGS, from_state
from orchestrator.infrastructure import kit
from orchestrator.infrastructure.settings import Settings

router = APIRouter(tags=["version"])

#: The release number lives in `VERSION` at the repository root, and the image lays the
#: repository out at `/app` (`backend-api/Dockerfile` copies it there), so the file is three
#: levels above this package in both places. Read as a file, not as distribution metadata:
#: PEP 440 normalises `1.0.0-beta` to `1.0.0b0`, and the number a client's kit records and
#: compares in its handshake is the file's spelling, never the normalised one.
VERSION_FILE = Path(orchestrator.__file__).resolve().parents[3] / "VERSION"
#: The distribution `pyproject.toml` names, the fallback when no `VERSION` file is beside it.
PACKAGE = "orchestrator"
#: What an uninstalled source tree without a `VERSION` file reports.
SOURCE_VERSION = "0.0.0+source"


def app_version() -> str:
    """`VERSION`'s content; failing that the distribution's; failing that a marker."""
    if VERSION_FILE.is_file():
        return VERSION_FILE.read_text().strip()
    try:
        return metadata_version(PACKAGE)
    except PackageNotFoundError:
        return SOURCE_VERSION


class HarnessVersions(BaseModel):
    """The CLI versions baked into this image, one per harness."""

    claude: str
    codex: str
    opencode: str


class VersionOut(BaseModel):
    """The `/api/v1/version` payload (AD-3).

    `kit_version` is what `GET /kit/archive` would hand out — `null` when this instance
    ships no kit, which only a source-tree run does.
    """

    app_version: str
    kit_version: str | None
    bmad_version: str
    harness_versions: HarnessVersions


def instance_settings(request: Request) -> Settings:
    settings: Settings = from_state(request, SETTINGS)
    return settings


@router.get("/version", response_model=VersionOut, summary="What this instance is")
def read_version(settings: Annotated[Settings, Depends(instance_settings)]) -> VersionOut:
    return VersionOut(
        app_version=app_version(),
        kit_version=kit.kit_version(settings.kit_dir),
        bmad_version=settings.bmad_version,
        harness_versions=HarnessVersions(
            claude=settings.claude_code_version,
            codex=settings.codex_version,
            opencode=settings.opencode_version,
        ),
    )
