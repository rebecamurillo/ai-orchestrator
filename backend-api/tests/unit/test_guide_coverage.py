"""Every `##` section and reference file of the orchestrator, initiative-spec and initiative-run
kit skills maps to a page of `guide/` (SPEC AC-6). Structure only — no page prose is asserted
(hard rule 6). Epic 3 story 3 deletes `test_fixture_covers_the_kit_skills` when it deletes the
skills.
"""

import json
from pathlib import Path

from tests.unit.conftest import REPO_ROOT

SKILLS = ("orchestrator", "initiative-spec", "initiative-run")
FIXTURE = Path(__file__).parent / "fixtures" / "kit_skill_sections.json"


def _page_ids() -> set[str]:
    guide = REPO_ROOT / "guide"
    return {p.relative_to(guide).with_suffix("").as_posix() for p in guide.rglob("*.md")}


def _kit_keys() -> set[str]:
    keys: set[str] = set()
    for skill in SKILLS:
        root = REPO_ROOT / "deploy" / "kit" / "skills" / skill
        in_fence = False
        for line in (root / "SKILL.md").read_text().splitlines():
            if line.startswith("```"):
                in_fence = not in_fence
            if not in_fence and line.startswith("## "):
                keys.add(f"{skill}/SKILL.md#{line[3:].rstrip()}")
        keys |= {f"{skill}/references/{p.name}" for p in (root / "references").glob("*.md")}
    return keys


def test_every_section_maps_to_a_guide_page() -> None:
    mapping = json.loads(FIXTURE.read_text())
    missing = {k: v for k, v in mapping.items() if v not in _page_ids()}
    assert not missing, f"fixture values that are not guide pages: {missing}"


def test_fixture_covers_the_kit_skills() -> None:
    mapping = json.loads(FIXTURE.read_text())
    keys = {k for k in mapping if k.split("/", 1)[0] in SKILLS}
    assert keys == _kit_keys()
