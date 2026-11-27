"""The upgrade page's initiative section (epic 9 story 3, AC9): structure only."""

from __future__ import annotations

import re

from tests.unit.conftest import REPO_ROOT

HEADING = "### Initiative conversations"
ORDER = ("/api/v1/instance/hold", "/api/v1/instance/upgrade-prepare", "./install.sh upgrade")


def test_the_page_names_the_three_commands_in_order_under_the_heading() -> None:
    text = (REPO_ROOT / "guide" / "host" / "upgrade.md").read_text()
    assert HEADING in text
    section = text.split(HEADING, 1)[1]
    positions = [section.index(token) for token in ORDER]
    assert positions == sorted(positions)


def test_the_readme_upgrade_block_carries_the_heading() -> None:
    readme = (REPO_ROOT / "deploy" / "README.md").read_text()
    match = re.search(r"^## Upgrading\n(.*?)(?=^## |\Z)", readme, re.S | re.M)
    assert match
    assert HEADING in match.group(1)
