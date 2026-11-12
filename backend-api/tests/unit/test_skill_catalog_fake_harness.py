"""The test-mode `fake` harness reads Claude's catalog (PR #19 review, 2026-11-12)."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.infrastructure.skill_catalog import FsSkillCatalog, manifest_path


def test_fake_reads_the_claude_manifest(tmp_path: Path) -> None:
    claude = tmp_path / ".claude" / "skills-manifest.json"
    claude.parent.mkdir(parents=True)
    claude.write_text(json.dumps({"skills": ["spec-gate", "staged-implement"]}))

    catalog = FsSkillCatalog(tmp_path)

    assert manifest_path(tmp_path, "fake") == claude
    assert catalog.installed_skills("fake") == catalog.installed_skills("claude")
    assert catalog.installed_skills("fake") == frozenset({"spec-gate", "staged-implement"})


def test_fake_without_a_claude_manifest_is_unavailable(tmp_path: Path) -> None:
    assert FsSkillCatalog(tmp_path).installed_skills("fake") is None
