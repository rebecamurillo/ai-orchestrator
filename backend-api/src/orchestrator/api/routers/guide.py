"""The guide, served open (AD-1 amended 2026-11-11): read-only, built files only.

`/llms.txt`, `/guide/{id}.md` and `/schemas/{name}.json` answer without the bearer so an agent
or editor learns how to use the instance before it holds the token. They read the build
directory `build_guide` wrote and nothing else: no settings, no database, no port.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response

import orchestrator
from orchestrator.api.errors import PROBLEM_MEDIA_TYPE, PROBLEM_SCHEMA_REF, Problem, ProblemDetail
from orchestrator.application import findings

router = APIRouter(tags=["guide"])

#: Beside `VERSION` (see `version.VERSION_FILE`); the image builds into `/app/guide-build`.
GUIDE_DIR = Path(orchestrator.__file__).resolve().parents[3] / "guide-build"

MARKDOWN = "text/markdown; charset=utf-8"
PLAIN = "text/plain; charset=utf-8"
SCHEMA = "application/schema+json"
SCHEMA_NAME = re.compile(r"[a-z0-9-]+")
HTTP_NOT_FOUND = 404


def guide_dir() -> Path:
    return GUIDE_DIR


def inside(root: Path, relative: str) -> Path | None:
    """`root / relative` resolved, or `None` when it leaves `root`."""
    resolved = (root / relative).resolve()
    return resolved if resolved.is_relative_to(root.resolve()) else None


def _unavailable() -> NoReturn:
    raise Problem(
        status=HTTP_NOT_FOUND,
        title="not found",
        detail=findings.entry(findings.REFUSAL_GUIDE_UNAVAILABLE).message,
        code=findings.REFUSAL_GUIDE_UNAVAILABLE,
        guide=findings.guide_id(findings.REFUSAL_GUIDE_UNAVAILABLE),
    )


def _index(root: Path) -> dict[str, Any]:
    try:
        document = json.loads((root / "guide-index.json").read_text(encoding="utf-8"))
    except OSError, ValueError:
        _unavailable()
    if not isinstance(document, dict) or not isinstance(document.get("pages"), list):
        _unavailable()
    return document


def _file(root: Path, relative: str) -> Path:
    path = inside(root, relative)
    if path is None or not path.is_file():
        _unavailable()
    return path


def _responses(media: str) -> dict[int | str, dict[str, Any]]:
    problem = {
        "model": ProblemDetail,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }
    return {
        200: {"content": {media: {"schema": {"type": "string"}}}},
        404: {**problem, "description": "No such page or schema, or no built guide."},
        422: {**problem, "description": "The request was refused before it was routed."},
    }


def _section(title: str, pages: list[dict[str, Any]]) -> list[str]:
    if not pages:
        return []
    return ["", f"## {title}", *(f"- [{p['title']}](/guide/{p['id']}.md)" for p in pages)]


@router.get(
    "/llms.txt",
    response_class=PlainTextResponse,
    responses=_responses(PLAIN),
    summary="The guide's index",
)
def read_index(root: Annotated[Path, Depends(guide_dir)]) -> PlainTextResponse:
    document = _index(root)
    try:
        pages = [
            {"id": str(p["id"]), "title": str(p["title"]), "audience": str(p["audience"])}
            for p in document["pages"]
        ]
        release = str(document["release"])
    except KeyError, TypeError:
        _unavailable()
    errors = [p for p in pages if p["id"].startswith("errors/")]
    rest = [p for p in pages if not p["id"].startswith("errors/")]
    lines = [
        "# ai-orchestrator guide",
        "",
        f"> The guide for release {release}. Every page is at /guide/{{id}}.md.",
        *_section("Guide", [p for p in rest if p["audience"] != "host"]),
        *_section("Host", [p for p in rest if p["audience"] == "host"]),
        *_section("Errors", errors),
    ]
    return PlainTextResponse("\n".join(lines) + "\n", media_type=PLAIN)


@router.get(
    "/guide/{page_id:path}.md",
    response_class=Response,
    responses=_responses(MARKDOWN),
    summary="One guide page",
)
def read_page(page_id: str, root: Annotated[Path, Depends(guide_dir)]) -> Response:
    pages = _index(root)["pages"]
    if page_id not in {p.get("id") for p in pages if isinstance(p, dict)}:
        _unavailable()
    text = _file(root, f"{page_id}.md").read_text(encoding="utf-8")
    return Response(text, media_type=MARKDOWN)


@router.get(
    "/schemas/{name}.json",
    response_class=Response,
    responses=_responses(SCHEMA),
    summary="One format description",
)
def read_schema(name: str, root: Annotated[Path, Depends(guide_dir)]) -> Response:
    if not SCHEMA_NAME.fullmatch(name):
        _unavailable()
    return Response(_file(root, f"schemas/{name}.json").read_bytes(), media_type=SCHEMA)
