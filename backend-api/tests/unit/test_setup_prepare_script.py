"""`scripts/setup/prepare.sh`: the folders a setup run mounts exist first (epic 5 story 1)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from tests.unit.conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "setup" / "prepare.sh"
HARNESS_DIR = REPO_ROOT / "scripts" / "harness"
HARNESSES = ("claude", "codex", "opencode")


def _run(home: Path, harness_dir: Path = HARNESS_DIR) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ["PATH"],
        "AGENT_HOME": str(home),
        "HARNESS_SCRIPTS_DIR": str(harness_dir),
    }
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )


def _asset_dirs() -> list[str]:
    out: list[str] = []
    for h in HARNESSES:
        res = subprocess.run(
            ["bash", str(HARNESS_DIR / f"{h}.sh"), "asset-dirs"],
            capture_output=True,
            text=True,
            check=True,
        )
        out.extend(res.stdout.split())
    return out


def _tree(home: Path) -> set[str]:
    return {str(p.relative_to(home)) for p in home.rglob("*")}


def test_script_is_committed_and_executable() -> None:
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)


def test_empty_home_gets_every_asset_dir_and_orchestrator(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    res = _run(home)
    assert res.returncode == 0, res.stderr
    claude = [".claude/skills", ".claude/agents", ".claude/commands"]
    expected = [*_asset_dirs(), *claude, ".orchestrator"]
    for d in expected:
        assert (home / d).is_dir(), d
    assert res.stdout.strip() != ""
    assert len(res.stdout.strip().splitlines()) >= len(set(expected))


def test_second_run_prints_nothing_and_changes_nothing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    assert _run(home).returncode == 0
    before = _tree(home)
    res = _run(home)
    assert res.returncode == 0
    assert res.stdout == ""
    assert _tree(home) == before


def _harness_copy(tmp_path: Path, bad_line: str) -> Path:
    copy = tmp_path / "harness"
    shutil.copytree(HARNESS_DIR, copy)
    (copy / "codex.sh").write_text(f'#!/usr/bin/env bash\necho "{bad_line}"\n')
    (copy / "codex.sh").chmod(0o755)
    return copy


def test_bad_asset_dir_lines_are_refused_before_any_mkdir(tmp_path: Path) -> None:
    for i, bad in enumerate(("/abs", "..", "../x", "a/../b", "")):
        home = tmp_path / f"home{i}"
        home.mkdir()
        res = _run(home, _copy(tmp_path, i, bad))
        assert res.returncode != 0, bad
        assert "codex.sh asset-dirs printed a bad path" in res.stderr, (bad, res.stderr)
        assert _tree(home) == set(), bad


def _copy(tmp_path: Path, i: int, bad: str) -> Path:
    base = tmp_path / f"h{i}"
    base.mkdir()
    return _harness_copy(base, bad)
