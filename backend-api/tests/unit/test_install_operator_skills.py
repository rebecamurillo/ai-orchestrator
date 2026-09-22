"""install_operator_skills: copies operator skills, detects collisions, writes manifest (story 4-1).

Shell logic lives entirely in `scripts/harness/_common.sh`; per-harness scripts only call
the shared function (AD-16). Tests here source `_common.sh` directly and call
`install_operator_skills` from a minimal wrapper, so every assertion is independent of
any harness CLI being installed.

AD-16 gitignore symmetry is also verified here: `.agents/skills/bmad-*` must be ignored
in parallel with the pre-existing `.claude/skills/bmad-*` rule.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

HARNESS_DIR = REPO_ROOT / "scripts" / "harness"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")


def _run_install(src: Path, dest: Path) -> subprocess.CompletedProcess[str]:
    """Source _common.sh and call install_operator_skills "$src" "$dest"."""
    wrapper = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'source "{HARNESS_DIR}/_common.sh"\n'
        f'install_operator_skills "{src}" "{dest}"\n'
    )
    return subprocess.run(  # fixed argv, no shell
        ["bash", "-c", wrapper],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": os.environ["PATH"],
            "HOME": os.environ.get("HOME", ""),
            "HARNESS_NAME": "test",
        },
    )


def _make_skill(base: Path, name: str) -> None:
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"# {name}\n")


# ── clean install ─────────────────────────────────────────────────────────────


def test_clean_install_copies_skills_and_writes_sorted_manifest(tmp_path: Path) -> None:
    """Skills copied with no collision; manifest contains union of stubs + operator, sorted."""
    src = tmp_path / "ia-agents-skills"
    dest = tmp_path / "skills"
    _make_skill(src, "my-skill-alpha")
    _make_skill(src, "my-skill-zeta")
    _make_skill(dest, "bmad-build-auto")
    _make_skill(dest, "bmad-dev-story")

    result = _run_install(src, dest)

    assert result.returncode == 0, result.stderr
    assert (dest / "my-skill-alpha").is_dir()
    assert (dest / "my-skill-zeta").is_dir()
    manifest = tmp_path / "skills-manifest.json"
    assert manifest.is_file()
    data = json.loads(manifest.read_text())
    assert data["skills"] == sorted(
        ["bmad-build-auto", "bmad-dev-story", "my-skill-alpha", "my-skill-zeta"]
    )


# ── collision detection ───────────────────────────────────────────────────────


def test_single_collision_exits_nonzero_and_names_the_skill(tmp_path: Path) -> None:
    """Single collision: exits non-zero, colliding name appears in stderr."""
    src = tmp_path / "ia-agents-skills"
    dest = tmp_path / "skills"
    _make_skill(src, "bmad-build-auto")  # collides with installed stub
    _make_skill(src, "my-safe-skill")
    _make_skill(dest, "bmad-build-auto")
    _make_skill(dest, "bmad-dev-story")

    result = _run_install(src, dest)

    assert result.returncode == 1
    assert "bmad-build-auto" in result.stderr


def test_multiple_collisions_all_listed_in_one_message(tmp_path: Path) -> None:
    """Two collisions: exits 1, both names appear in one error message in stderr."""
    src = tmp_path / "ia-agents-skills"
    dest = tmp_path / "skills"
    _make_skill(src, "bmad-build-auto")  # collides
    _make_skill(src, "bmad-dev-story")  # collides
    _make_skill(src, "my-safe-skill")
    _make_skill(dest, "bmad-build-auto")
    _make_skill(dest, "bmad-dev-story")
    _make_skill(dest, "bmad-code-review")

    result = _run_install(src, dest)

    assert result.returncode == 1
    # Both names must appear (all collisions reported in one shot, not one per rebuild)
    assert "bmad-build-auto" in result.stderr
    assert "bmad-dev-story" in result.stderr


# ── empty operator skills ─────────────────────────────────────────────────────


def test_empty_operator_skills_produces_manifest_with_stubs_only(tmp_path: Path) -> None:
    """No subdirs in ia-agents-skills (only README.md): manifest has only BMAD stub names."""
    src = tmp_path / "ia-agents-skills"
    src.mkdir()
    (src / "README.md").write_text("# Operator Skills\n")
    dest = tmp_path / "skills"
    _make_skill(dest, "bmad-build-auto")
    _make_skill(dest, "bmad-dev-story")

    result = _run_install(src, dest)

    assert result.returncode == 0, result.stderr
    manifest = tmp_path / "skills-manifest.json"
    assert manifest.is_file()
    data = json.loads(manifest.read_text())
    assert data["skills"] == sorted(["bmad-build-auto", "bmad-dev-story"])


# ── gitignore symmetry (AD-16) ────────────────────────────────────────────────


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_agents_skills_bmad_entries_are_gitignored() -> None:
    """`.agents/skills/bmad-*` is ignored symmetrically with `.claude/skills/bmad-*` (AD-16)."""
    result = subprocess.run(  # fixed argv, no shell
        ["git", "check-ignore", "-q", "--no-index", ".agents/skills/bmad-build-auto"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        pytest.fail(f"git check-ignore failed: {result.stderr}")
    assert result.returncode == 0, ".agents/skills/bmad-* must be gitignored (AD-16)"


# ── harness wiring (AD-16) ────────────────────────────────────────────────────


@pytest.mark.parametrize("harness", ("claude", "codex", "opencode"))
def test_harness_install_calls_install_operator_skills(harness: str) -> None:
    """install() in claude.sh, codex.sh, opencode.sh must call install_operator_skills (AD-16)."""
    content = (HARNESS_DIR / f"{harness}.sh").read_text()
    assert "install_operator_skills" in content, (
        f"{harness}.sh must call install_operator_skills in install()"
    )
