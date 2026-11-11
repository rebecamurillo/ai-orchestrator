"""The release's `bmad-method` installs no skill named like an operator skill (SPEC CAP-2).

BMAD no longer reaches a harness home at image build, so the collision the build used to catch
is checked here: install the pinned package into a scratch prefix, run its installer into a
scratch directory, and compare the skill folders it wrote with `ia-agents-skills/`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "scripts" / "harness" / "_common.sh"
OPERATOR_SKILLS = ROOT / "ia-agents-skills"
SKILL_FOLDERS = (".claude/skills", ".agents/skills")


def _bmad_version() -> str:
    match = re.search(r"\$\{BMAD_VERSION:=([^}]+)\}", COMMON.read_text())
    assert match is not None, "BMAD_VERSION default not found in _common.sh"
    return match.group(1)


def test_no_bmad_skill_name_equals_an_operator_skill(tmp_path: Path) -> None:
    npm = shutil.which("npm")
    if npm is None:
        pytest.fail("npm is not on PATH: this check installs bmad-method")
    prefix = tmp_path / "prefix"
    scratch = tmp_path / "project"
    scratch.mkdir()
    subprocess.run(
        [npm, "install", "-g", "--prefix", str(prefix), f"bmad-method@{_bmad_version()}"],
        check=True,
    )
    subprocess.run(
        ["git", "init", "-q", str(scratch)],
        check=True,
    )
    subprocess.run(
        [
            str(prefix / "bin" / "bmad-method"),
            "install",
            "--yes",
            "--modules",
            "bmm",
            "--tools",
            "claude-code,codex,opencode",
            "--directory",
            str(scratch),
        ],
        check=True,
    )

    written = [folder for folder in SKILL_FOLDERS if (scratch / folder).is_dir()]
    assert written, f"bmad-method wrote none of {SKILL_FOLDERS}: the comparison would be vacuous"
    operator = {p.name for p in OPERATOR_SKILLS.iterdir() if p.is_dir()}
    installed = {
        f"{folder}/{p.name}"
        for folder in written
        for p in (scratch / folder).iterdir()
        if p.is_dir() and p.name in operator
    }

    assert not installed, (
        f"bmad-method {_bmad_version()} installs operator skill names: {sorted(installed)}"
    )
