"""`GET /api/v1/version` — what this instance is: the C1 version answer (AD-33).

The answer names the instance's release, its bootstrap contract and where its guide is, plus
the pinned tool versions `Settings` already carries (AD-16). A release difference never stops a
client; only `bootstrap_contract` above the one a bootstrap states is reported.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as metadata_version
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

import orchestrator
from orchestrator.api.providers_base import SETTINGS, from_state, setup_record
from orchestrator.application.setup_summary import bmad_installed
from orchestrator.domain.ports.setup_record import SetupRecord
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


#: The frozen bootstrap contract number (AD-33, C1); raised only by a contract change.
BOOTSTRAP_CONTRACT = 1


class GuideRefs(BaseModel):
    """Where this instance's guide is (C1): the index, the page route and the MCP resource."""

    index: str
    page_url: str
    resource: str


class VersionOut(BaseModel):
    """The `/api/v1/version` payload (AD-3).

    `bootstrap_contract` is the C1 contract number and `guide` the three guide addresses.
    `kit_version` is always `null`: the key stays so beta.4 kit skills still parse the answer
    (AD-33). `bmad_installed` is what the last setup run installed (`null` when none did),
    `bmad_version` the release pin.
    """

    app_version: str
    bootstrap_contract: int
    guide: GuideRefs
    kit_version: str | None
    bmad_version: str
    bmad_installed: str | None = None
    harness_versions: HarnessVersions


def instance_settings(request: Request) -> Settings:
    settings: Settings = from_state(request, SETTINGS)
    return settings


@router.get("/version", response_model=VersionOut, summary="What this instance is")
def read_version(
    settings: Annotated[Settings, Depends(instance_settings)],
    record: Annotated[SetupRecord, Depends(setup_record)],
) -> VersionOut:
    return VersionOut(
        app_version=app_version(),
        bootstrap_contract=BOOTSTRAP_CONTRACT,
        guide=GuideRefs(index="/llms.txt", page_url="/guide/{id}.md", resource="guide://{id}"),
        kit_version=None,
        bmad_version=settings.bmad_version,
        bmad_installed=bmad_installed(record.read()),
        harness_versions=HarnessVersions(
            claude=settings.claude_code_version,
            codex=settings.codex_version,
            opencode=settings.opencode_version,
        ),
    )
