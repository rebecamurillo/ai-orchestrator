"""`FsSkillCatalog` reads one manifest per harness (story 1, orchestrator-deploy-folder epic 1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.infrastructure.skill_catalog import FsSkillCatalog, manifest_path

PATHS = {
    "claude": ".claude/skills-manifest.json",
    "codex": ".agents/skills-manifest.json",
    "opencode": ".config/opencode/skills-manifest.json",
    "local": ".config/opencode/skills-manifest.json",
}


def write(home: Path, relative: str, skills: list[str]) -> None:
    path = home / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"skills": skills}))


@pytest.mark.parametrize("harness", sorted(PATHS))
def test_each_harness_reads_its_own_manifest(tmp_path: Path, harness: str) -> None:
    for relative in PATHS.values():
        write(tmp_path, relative, [f"only-{relative}"])

    assert FsSkillCatalog(tmp_path).installed_skills(harness) == frozenset(
        {f"only-{PATHS[harness]}"}
    )
    assert manifest_path(tmp_path, harness) == tmp_path / PATHS[harness]


def test_local_and_opencode_share_one_manifest(tmp_path: Path) -> None:
    write(tmp_path, PATHS["opencode"], ["a"])

    catalog = FsSkillCatalog(tmp_path)

    assert catalog.installed_skills("local") == catalog.installed_skills("opencode") == {"a"}


def test_an_unknown_harness_has_no_catalog(tmp_path: Path) -> None:
    write(tmp_path, PATHS["claude"], ["a"])

    assert manifest_path(tmp_path, "gemini") is None
    assert FsSkillCatalog(tmp_path).installed_skills("gemini") is None


def test_a_malformed_manifest_is_unavailable_for_its_harness_only(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "skills-manifest.json").write_text("{")
    write(tmp_path, PATHS["codex"], ["a"])

    catalog = FsSkillCatalog(tmp_path)

    assert catalog.installed_skills("claude") is None
    assert catalog.installed_skills("codex") == frozenset({"a"})
