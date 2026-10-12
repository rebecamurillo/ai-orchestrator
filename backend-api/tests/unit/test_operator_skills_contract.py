"""`ia-agents-skills/README.md`'s authoring contract, checked: one directory per skill, a
`SKILL.md` in each whose frontmatter `name` is the directory, and — for the staged family —
the `spec_folder` / `story_id` args the `staged-*` templates dispatch with."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

#: `tests/unit/test_operator_skills_contract.py` -> the repository root.
SKILLS_DIR = Path(__file__).resolve().parents[3] / "ia-agents-skills"
STAGED_ARGS = {"spec_folder", "story_id"}


def skill_dirs() -> list[Path]:
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())


def frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text()
    assert text.startswith("---\n"), path
    _, block, _ = text.split("---\n", 2)
    loaded = yaml.safe_load(block)
    assert isinstance(loaded, dict)
    return loaded


@pytest.mark.parametrize("directory", skill_dirs(), ids=lambda p: p.name)
def test_every_operator_skill_has_an_entry_point_named_after_its_directory(
    directory: Path,
) -> None:
    entry = directory / "SKILL.md"
    assert entry.is_file(), directory.name
    assert frontmatter(entry)["name"] == directory.name


@pytest.mark.parametrize(
    "directory", [p for p in skill_dirs() if p.name.startswith("staged-")], ids=lambda p: p.name
)
def test_every_staged_skill_declares_the_two_dispatch_args(directory: Path) -> None:
    args = frontmatter(directory / "SKILL.md")["args"]
    assert isinstance(args, dict)
    assert set(args) == STAGED_ARGS, directory.name


def test_the_three_staged_stages_ship() -> None:
    assert {p.name for p in skill_dirs() if p.name.startswith("staged-")} == {
        "staged-plan",
        "staged-implement",
        "staged-review",
    }
