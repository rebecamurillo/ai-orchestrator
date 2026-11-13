"""Every value of the frozen AC-6 list (`kit_skill_sections.json`) is a guide page (SPEC AC-6).
Structure only — no page prose is asserted (hard rule 6). Epic 3 story 3, 2026-11-12 (AD-33): the
kit skills are deleted, so the test that compared the list with their sections is gone.
"""

import json
from pathlib import Path

from tests.unit.conftest import REPO_ROOT

FIXTURE = Path(__file__).parent / "fixtures" / "kit_skill_sections.json"


def _page_ids() -> set[str]:
    guide = REPO_ROOT / "guide"
    return {p.relative_to(guide).with_suffix("").as_posix() for p in guide.rglob("*.md")}


def test_every_section_maps_to_a_guide_page() -> None:
    mapping = json.loads(FIXTURE.read_text())
    missing = {k: v for k, v in mapping.items() if v not in _page_ids()}
    assert not missing, f"fixture values that are not guide pages: {missing}"
