"""The product's BMAD script (SPEC CAP-4, owner D-6) on scratch homes with stub packages."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "bmad" / "install.sh"
RUNNER = ROOT / "scripts" / "setup" / "run.sh"
COMMON = ROOT / "scripts" / "harness" / "_common.sh"
HARNESSES = ("claude", "codex", "opencode")
SKILLS = {
    "claude": ".claude/skills",
    "codex": ".agents/skills",
    "opencode": ".config/opencode/skills",
}
BAD_INSTALLER = 5

STUB_HARNESS = """#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_common.sh"
{assets}
case "${{1:-}}" in
  asset-dirs) printf '%s\\n' "${{ASSET_DIRS[@]}}" ;;
  *) exit 2 ;;
esac
"""

STUB_BIN = """#!/usr/bin/env bash
set -euo pipefail
tools=""; dir=""
while [ $# -gt 0 ]; do
  case "$1" in
    --tools) tools="$2"; shift 2 ;;
    --directory) dir="$2"; shift 2 ;;
    *) shift ;;
  esac
done
{exit_line}
if [ "$tools" = claude-code ]; then base="$dir/.claude/skills"; else base="$dir/.agents/skills"; fi
for name in {names}; do
  mkdir -p "$base/$name"
  echo "{letter} $name" > "$base/$name/SKILL.md"
done
"""


class Scratch:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.home.mkdir()
        self.harness = root / "harness"
        self.harness.mkdir()
        shutil.copy(COMMON, self.harness / "_common.sh")
        for name in HARNESSES:
            text = (ROOT / "scripts" / "harness" / f"{name}.sh").read_text()
            line = next(ln for ln in text.splitlines() if ln.startswith("ASSET_DIRS="))
            stub = self.harness / f"{name}.sh"
            stub.write_text(STUB_HARNESS.format(assets=line))
            stub.chmod(0o755)
        self.shim = root / "shim"
        self.shim.mkdir()
        self.marker = root / "network-used"
        for tool in ("npx", "npm"):
            path = self.shim / tool
            path.write_text(f"#!/bin/sh\ntouch '{self.marker}'\nexit 97\n")
            path.chmod(0o755)
        self.package("A", "bmad-a1 bmad-common")
        self.package("B", "bmad-b1 bmad-common")

    def package(self, letter: str, names: str, *, exit_code: int = 0) -> Path:
        pkg = self.root / f"pkg{letter}"
        (pkg / "bin").mkdir(parents=True, exist_ok=True)
        exit_line = f"exit {exit_code}" if exit_code else ""
        bin_ = pkg / "bin" / "bmad-method"
        bin_.write_text(STUB_BIN.format(exit_line=exit_line, names=names, letter=letter))
        bin_.chmod(0o755)
        return pkg

    def env(self, letter: str, **extra: str) -> dict[str, str]:
        return {
            "PATH": f"{self.shim}:{os.environ['PATH']}",
            "AGENT_HOME": str(self.home),
            "HARNESS_SCRIPTS_DIR": str(self.harness),
            "BMAD_PREFIX": str(self.root / f"pkg{letter}"),
            "BMAD_VERSION": letter,
            **extra,
        }

    def run(self, letter: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            env=self.env(letter),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def skills(self, harness: str) -> Path:
        return self.home / SKILLS[harness]

    def names(self, harness: str) -> list[str]:
        folder = self.skills(harness)
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []

    @property
    def record_path(self) -> Path:
        return self.home / ".orchestrator" / "bmad.json"

    def snapshot(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for path in sorted(self.home.rglob("*")):
            rel = path.relative_to(self.home).as_posix()
            out[rel] = path.read_text() if path.is_file() else "<dir>"
        return out


def _entries(*names: str) -> dict[str, list[str]]:
    return {h: sorted(names) for h in HARNESSES}


def test_upgrade_replaces_the_previous_package(tmp_path: Path) -> None:
    s = Scratch(tmp_path)
    first = s.run("A")
    assert first.returncode == 0, first.stderr
    second = s.run("B")
    assert second.returncode == 0, second.stderr
    for harness in HARNESSES:
        assert s.names(harness) == ["bmad-b1", "bmad-common"]
        assert (s.skills(harness) / "bmad-common" / "SKILL.md").read_text() == "B bmad-common\n"
    assert json.loads(s.record_path.read_text()) == {
        "version": "B",
        "entries": _entries("bmad-b1", "bmad-common"),
    }
    assert not s.marker.exists()


def test_no_record_adopts_every_bmad_entry_of_the_asset_folders(tmp_path: Path) -> None:
    s = Scratch(tmp_path)
    (s.skills("claude") / "bmad-old").mkdir(parents=True)
    (s.home / ".claude" / "commands" / "bmad-old").mkdir(parents=True)
    result = s.run("B")
    assert result.returncode == 0, result.stderr
    assert not (s.skills("claude") / "bmad-old").exists()
    assert not (s.home / ".claude" / "commands" / "bmad-old").exists()
    for harness in HARNESSES:
        assert s.names(harness) == ["bmad-b1", "bmad-common"]
    assert json.loads(s.record_path.read_text())["entries"] == _entries("bmad-b1", "bmad-common")


def test_client_skills_and_logins_are_untouched(tmp_path: Path) -> None:
    s = Scratch(tmp_path)
    mine = {
        s.skills("claude") / "my-skill" / "SKILL.md": "# mine\n",
        s.skills("codex") / "my-skill" / "SKILL.md": "# mine too\n",
        s.home / ".claude" / ".credentials.json": '{"token": "stub"}',
    }
    for path, text in mine.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    for letter in ("A", "B"):
        result = s.run(letter)
        assert result.returncode == 0, result.stderr
        for path, text in mine.items():
            assert path.read_text() == text


def test_failing_installer_changes_nothing(tmp_path: Path) -> None:
    s = Scratch(tmp_path)
    assert s.run("A").returncode == 0
    before = s.snapshot()

    s.package("B", "bmad-b1", exit_code=BAD_INSTALLER)
    failed = s.run("B")
    assert failed.returncode != 0
    assert "bmad-method" in failed.stderr
    assert s.snapshot() == before

    shutil.rmtree(tmp_path / "pkgB")
    missing = s.run("B")
    assert missing.returncode != 0
    assert "bmad package not found" in missing.stderr
    assert s.snapshot() == before
    assert not s.marker.exists()


def test_unsafe_or_unreadable_record_deletes_nothing(tmp_path: Path) -> None:
    s = Scratch(tmp_path)
    keep = s.skills("claude") / "bmad-keep"
    keep.mkdir(parents=True)
    (keep / "SKILL.md").write_text("keep\n")
    s.record_path.parent.mkdir(parents=True)
    bad_records = [
        json.dumps({"version": "A", "entries": {"claude": ["../.."]}}),
        json.dumps({"version": "A", "entries": {"claude": ["a/b"]}}),
        json.dumps({"version": "A", "entries": {"claude": [".."]}}),
        json.dumps({"version": "A", "entries": {"claude": ["x\nclaude\t.."]}}),
        json.dumps({"version": "A", "entries": {"claude\t..\nx": ["y"]}}),
        "{not json",
    ]
    for text in bad_records:
        s.record_path.write_text(text)
        before = s.snapshot()
        result = s.run("B")
        assert result.returncode != 0
        assert s.snapshot() == before
        assert s.record_path.read_text() == text


def test_the_runner_records_the_installed_version(tmp_path: Path) -> None:
    s = Scratch(tmp_path)
    logs = tmp_path / "logs"
    client = tmp_path / "client-setup"
    src = tmp_path / "skills-src"
    for folder in (logs, client, src):
        folder.mkdir()
    env = {
        **s.env("B"),
        "CLIENT_SETUP_DIR": str(client),
        "BMAD_SCRIPT_DIR": str(ROOT / "deploy" / "bmad"),
        "SETUP_LOG_DIR": str(logs),
        "OPERATOR_SKILLS_SRC": str(src),
        "ORCH_SETUP_TRIGGER": "install",
        "ORCH_RELEASE": "1.2.3",
    }
    result = subprocess.run(
        ["bash", str(RUNNER)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    record = json.loads((s.home / ".orchestrator" / "setup-run.json").read_text())
    assert record["bmad"] == {"choice": "installed", "version": "B", "ok": True}
    for harness in HARNESSES:
        manifest = json.loads((s.skills(harness).parent / "skills-manifest.json").read_text())
        assert {"bmad-b1", "bmad-common"} <= set(manifest["skills"])
