"""The kit holds the bootstrap, its installer and the MCP templates, and nothing else
(epic 3 story 3, 2026-11-12, AD-33): no skills, no bin/, and no document names what left.
"""

from __future__ import annotations

import io
import json
import re
import tarfile

from orchestrator.infrastructure import kit
from tests.unit.conftest import REPO_ROOT

KIT = REPO_ROOT / "deploy" / "kit"
RETIRED = ("orchestrator-watch", "references/workflows.md", "kit/skills/")
#: Token shapes, each length-bounded: a bare `sk-` would fire on prose like "risk-free".
SECRETS = (
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b[0-9a-f]{64}\b"),
)
REQUIRED = (
    "bootstrap/SKILL.md.tmpl",
    "install.sh",
    "mcp/claude.json",
    "mcp/codex.toml",
    "mcp/opencode.json",
)


def _members() -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(kit.archive(KIT))) as tar:
        return [m.name.removeprefix("./") for m in tar.getmembers()]


def test_the_archive_holds_no_skills_and_no_bin() -> None:
    names = _members()

    assert not [n for n in names if n.startswith(("skills/", "bin/"))]
    for required in REQUIRED:
        assert required in names, required


def test_no_guide_page_or_kit_file_names_a_retired_file() -> None:
    hits = []
    for root in (REPO_ROOT / "guide", KIT):
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            text = path.read_text(errors="ignore")
            hits += [f"{path.relative_to(REPO_ROOT)}: {term}" for term in RETIRED if term in text]

    assert not hits, hits


def test_the_manifest_carries_the_version_and_no_skills() -> None:
    manifest = json.loads((KIT / "manifest.json").read_text())

    assert "kit_version" in manifest
    assert "skills" not in manifest


def test_no_guide_page_or_kit_file_carries_a_token_shaped_string() -> None:
    """The guide is served to every agent; the skills' token scan moves to what replaced them."""
    hits = [
        f"{path.relative_to(REPO_ROOT)}: {pattern.pattern}"
        for root in (REPO_ROOT / "guide", KIT)
        for path in sorted(p for p in root.rglob("*") if p.is_file())
        for pattern in SECRETS
        if pattern.search(path.read_text(errors="ignore"))
    ]

    assert not hits, f"credential-shaped strings (hard rule 5): {hits}"
