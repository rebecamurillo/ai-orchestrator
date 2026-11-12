"""Host pages and the README's generated sections: structure only (hard rule 6, AD-32, story 6)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from check_guide import HOST_LINE, parse_page

from tests.unit.conftest import REPO_ROOT

GUIDE = REPO_ROOT / "guide"
README = (REPO_ROOT / "deploy" / "README.md").read_text()
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "kit_skill_sections.json").read_text())
README_KEYS = {
    k.split("#", 1)[1]: v for k, v in FIXTURE.items() if k.startswith("deploy/README.md#")
}
BLOCKS = (
    "Install",
    "Day 2",
    "Setup scripts and BMAD",
    "Upgrading",
    "Editing the workflow templates",
)
POINTERS = ("Docker for Runs (optional, off by default)", "Notifications", "Trust")


def _section(heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", README, re.S | re.M)
    assert match, heading
    return match.group(1).strip()


def test_every_host_page_opens_on_the_host_line() -> None:
    pages = sorted((GUIDE / "host").glob("*.md"))
    assert pages
    for path in pages:
        meta, body, error = parse_page(path.read_text())
        assert meta is not None, error
        assert meta["audience"] == "host", path
        assert body.lstrip("\n").split("\n", 1)[0] == HOST_LINE, path


def test_every_host_audience_page_lies_under_host() -> None:
    for path in GUIDE.rglob("*.md"):
        meta, _, _ = parse_page(path.read_text())
        if meta and meta.get("audience") == "host":
            assert path.relative_to(GUIDE).parts[0] == "host", path


def test_the_readme_keys_of_the_fixture_are_readme_headings() -> None:
    headings = {line[3:].rstrip() for line in README.splitlines() if line.startswith("## ")}
    assert set(README_KEYS) <= headings


def test_the_generated_sections_are_one_block_of_their_page() -> None:
    for heading in BLOCKS:
        page_id = README_KEYS[heading]
        meta, _, _ = parse_page((GUIDE / f"{page_id}.md").read_text())
        assert meta is not None
        block = re.fullmatch(
            rf"<!-- guide:{re.escape(meta['readme'])} -->.*<!-- /guide -->", _section(heading), re.S
        )
        assert block, heading
        assert _section(heading).count("<!-- guide:") == 1, heading


def test_the_pointer_sections_are_one_line_naming_their_page() -> None:
    for heading in POINTERS:
        page_id = README_KEYS[heading]
        pointer = f"On a running instance: `$ORCHESTRATOR_BASE_URL/guide/{page_id}.md`."
        assert _section(heading) == pointer
