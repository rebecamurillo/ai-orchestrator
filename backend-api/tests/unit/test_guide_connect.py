"""The connecting page and the README agents section (epic 3 story 4, 2026-11-13)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from check_guide import parse_page

from tests.unit.conftest import REPO_ROOT

README = (REPO_ROOT / "deploy" / "README.md").read_text()
HEADING = "Agents in your projects"
META, BODY, _ERROR = parse_page((REPO_ROOT / "guide" / "connect.md").read_text())
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "kit_skill_sections.json").read_text())


def _section(heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", README, re.S | re.M)
    assert match, heading
    return match.group(1).strip()


def test_the_page_is_any_audience_and_feeds_the_agents_section() -> None:
    assert META is not None, _ERROR
    assert META["audience"] == "any"
    assert META["readme"] == "agents"


def test_the_readme_section_is_one_block_equal_to_the_page_body() -> None:
    match = re.fullmatch(r"<!-- guide:agents -->\n(.*)\n<!-- /guide -->", _section(HEADING), re.S)
    assert match
    assert match.group(1).strip() == BODY.strip()


def test_the_page_names_the_installer_the_token_the_risk_and_the_move() -> None:
    for needle in (
        '/api/v1/kit/install.sh" | bash -s -- --harness',
        "ORCHESTRATOR_TOKEN",
        "`harness-support`",
        "beta.4",
        "refusal-bootstrap-contract",
    ):
        assert needle in BODY, needle
    assert re.search(r"one token", BODY, re.I)


def test_every_bearer_is_a_variable_reference() -> None:
    assert "Bearer " in BODY
    for match in re.finditer(r"Bearer (.)", BODY):
        assert match.group(1) == "$"


def test_no_sentence_stops_on_a_release_difference() -> None:
    pattern = r"\bstop\W+(?:\w+\W+){0,3}?(?:mismatch|differ\w*|disagree\w*)"
    assert not re.search(pattern, BODY, re.I)


def test_the_page_has_no_heading_that_would_split_the_readme_section() -> None:
    assert not re.search(r"^#{1,2} ", BODY, re.M)


def test_the_fixture_maps_the_readme_section_to_the_page() -> None:
    assert FIXTURE[f"deploy/README.md#{HEADING}"] == "connect"
