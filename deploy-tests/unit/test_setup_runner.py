"""The setup runner (SPEC CAP-3, AD-28): five phases on scratch homes with stub scripts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from orchestrator.domain.entities.setup_run import SetupRun

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "setup" / "run.sh"
COMMON = ROOT / "scripts" / "harness" / "_common.sh"
FAILED = 2
TIMED_OUT = 124
BMAD_EXIT = 3
HARNESSES = ("claude", "codex", "opencode")
SKILLS = {
    "claude": ".claude/skills",
    "codex": ".agents/skills",
    "opencode": ".config/opencode/skills",
}

STUB_HARNESS = """#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_common.sh"
{assets}
case "${{1:-}}" in
  asset-dirs) printf '%s\\n' "${{ASSET_DIRS[@]}}" ;;
  *) exit 2 ;;
esac
"""


@dataclass
class Scratch:
    root: Path

    @property
    def home(self) -> Path:
        return self.root / "home"

    @property
    def client(self) -> Path:
        return self.root / "client-setup"

    @property
    def bmad(self) -> Path:
        return self.root / "bmad"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def src(self) -> Path:
        return self.root / "skills-src"

    def skills(self, harness: str = "claude") -> Path:
        return self.home / SKILLS[harness]

    def script(self, name: str, body: str, *, mode: int = 0o755) -> Path:
        path = self.client / name
        path.write_text("#!/usr/bin/env bash\n" + body + "\n")
        path.chmod(mode)
        return path

    def run(self, *args: str, timeout: int = 60, **env: str) -> subprocess.CompletedProcess[str]:
        environ = {
            "PATH": os.environ["PATH"],
            "AGENT_HOME": str(self.home),
            "CLIENT_SETUP_DIR": str(self.client),
            "BMAD_SCRIPT_DIR": str(self.bmad),
            "SETUP_LOG_DIR": str(self.logs),
            "OPERATOR_SKILLS_SRC": str(self.src),
            "HARNESS_SCRIPTS_DIR": str(self.root / "harness"),
            "BMAD_VERSION": "9.9.9",
            "ORCH_SETUP_TRIGGER": "install",
            "ORCH_RELEASE": "1.2.3",
            **env,
        }
        return subprocess.run(
            ["bash", str(RUNNER), *args],
            env=environ,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def record(self) -> dict:
        return json.loads((self.home / ".orchestrator" / "setup-run.json").read_text())

    def skill_dirs(self, harness: str = "claude") -> list[str]:
        """Epic 5 story 2, 2026-11-11 AD-16/AD-28 amendment: the folder is counted."""
        return sorted(p.name for p in self.skills(harness).iterdir() if p.is_dir())


def _asset_line(harness: str) -> str:
    text = (ROOT / "scripts" / "harness" / f"{harness}.sh").read_text()
    return next(line for line in text.splitlines() if line.startswith("ASSET_DIRS="))


def _scratch(tmp_path: Path) -> Scratch:
    s = Scratch(tmp_path)
    for folder in (s.home, s.client, s.bmad, s.logs):
        folder.mkdir()
    harness = tmp_path / "harness"
    harness.mkdir()
    shutil.copy(COMMON, harness / "_common.sh")
    for name in HARNESSES:
        stub = harness / f"{name}.sh"
        stub.write_text(STUB_HARNESS.format(assets=_asset_line(name)))
        stub.chmod(0o755)
    for skill in ("staged-plan", "senior-consult"):
        (s.src / skill).mkdir(parents=True)
        (s.src / skill / "SKILL.md").write_text(f"# {skill}\n")
    install = s.bmad / "install.sh"
    install.write_text("#!/usr/bin/env bash\nexit 0\n")
    install.chmod(0o755)
    return s


def test_all_succeed_writes_a_valid_record(tmp_path: Path) -> None:
    s = _scratch(tmp_path)
    s.script("10-ok.sh", "exit 0")
    result = s.run()
    assert result.returncode == 0, result.stderr
    raw = json.loads((s.home / ".orchestrator" / "setup-run.json").read_text())
    record = SetupRun.model_validate(raw)
    assert raw["at"].endswith("Z")
    assert (record.trigger, record.release) == ("install", "1.2.3")
    assert record.bmad.ok is True
    assert record.bmad.choice == "installed"
    assert record.operator.ok is True
    assert [script.name for script in record.scripts] == ["10-ok.sh"]
    assert raw["scripts"][0]["log"].startswith("logs/setup/") and raw["scripts"][0]["log"].endswith(
        "/10-ok.sh.log"
    )
    for harness in HARNESSES:
        assert getattr(record.catalog, harness) == len(s.skill_dirs(harness))
    assert list((s.home / ".orchestrator").glob("*.tmp*")) == []


def test_client_skill_is_counted_in_the_catalog(tmp_path: Path) -> None:
    s = _scratch(tmp_path)
    s.script(
        "10-skill.sh",
        'mkdir -p "$HOME/.claude/skills/s" && echo x > "$HOME/.claude/skills/s/SKILL.md"',
    )
    assert s.run().returncode == 0
    assert "s" in s.skill_dirs("claude")
    assert s.record()["catalog"]["claude"] == len(s.skill_dirs("claude"))
    entry = s.record()["scripts"][0]
    assert (entry["ok"], entry["exit"], entry["clashes"]) == (True, 0, [])


def test_phase_4_writes_no_manifest() -> None:
    """Epic 5 story 2, 2026-11-11 AD-16/AD-28 amendment: backend-api alone writes the catalog."""
    lines = [ln for ln in RUNNER.read_text().splitlines() if not ln.strip().startswith("#")]
    assert [ln for ln in lines if "write_skills_manifest" in ln] == []


def test_failing_script_does_not_stop_the_next(tmp_path: Path) -> None:
    s = _scratch(tmp_path)
    s.script("10-bad.sh", "echo boom; exit 1")
    s.script("20-good.sh", "exit 0")
    result = s.run()
    assert result.returncode == FAILED
    scripts = s.record()["scripts"]
    assert [x["name"] for x in scripts] == ["10-bad.sh", "20-good.sh"]
    assert [x["ok"] for x in scripts] == [False, True]
    assert scripts[0]["exit"] == 1
    stamp = next(s.logs.iterdir())
    assert (stamp / "10-bad.sh.log").read_text().strip() == "boom"
    assert (stamp / "20-good.sh.log").exists()


def test_timeout_marks_the_script_and_continues(tmp_path: Path) -> None:
    s = _scratch(tmp_path)
    s.script("10-slow.sh", "sleep 30")
    s.script("20-after.sh", "exit 0")
    result = s.run(timeout=30, SETUP_SCRIPT_TIMEOUT="1")
    assert result.returncode == FAILED
    scripts = s.record()["scripts"]
    assert (scripts[0]["exit"], scripts[0]["ok"]) == (TIMED_OUT, False)
    assert scripts[1]["ok"] is True


def test_overwriting_an_operator_skill_and_creating_a_bmad_name_are_restored(
    tmp_path: Path,
) -> None:
    s = _scratch(tmp_path)
    s.script(
        "10-clash.sh",
        "S=$HOME/.claude/skills; rm -rf $S/staged-plan; mkdir -p $S/staged-plan $S/bmad-help\n"
        "echo evil > $S/staged-plan/SKILL.md; echo x > $S/bmad-help/SKILL.md",
    )
    # The product's copy is on top before the script runs (a previous setup, or an image seed).
    shutil.copytree(s.src / "staged-plan", s.skills() / "staged-plan")
    result = s.run()
    assert result.returncode == FAILED
    assert (s.skills() / "staged-plan" / "SKILL.md").read_text() == "# staged-plan\n"
    assert not (s.skills() / "bmad-help").exists()
    entry = s.record()["scripts"][0]
    assert entry["ok"] is False
    assert entry["clashes"] == ["bmad-help", "staged-plan"]


def test_clash_in_a_non_claude_harness_folder_is_restored(tmp_path: Path) -> None:
    s = _scratch(tmp_path)
    s.script(
        "10-codex.sh",
        'mkdir -p "$HOME/.agents/skills/bmad-x"; echo 1 > "$HOME/.agents/skills/bmad-x/SKILL.md"',
    )
    assert s.run().returncode == FAILED
    assert not (s.skills("codex") / "bmad-x").exists()
    assert s.record()["scripts"][0]["clashes"] == ["bmad-x"]


def test_script_deleting_a_skills_folder_is_restored_and_recorded(tmp_path: Path) -> None:
    s = _scratch(tmp_path)
    s.script("10-wipe.sh", 'rm -rf "$HOME/.claude/skills"')
    shutil.copytree(s.src / "staged-plan", s.skills() / "staged-plan")
    result = s.run()
    assert result.returncode == FAILED
    assert (s.skills() / "staged-plan" / "SKILL.md").read_text() == "# staged-plan\n"
    entry = s.record()["scripts"][0]
    assert (entry["ok"], entry["clashes"]) == (False, ["staged-plan"])


def test_reset_empties_asset_folders_and_keeps_everything_else(tmp_path: Path) -> None:
    s = _scratch(tmp_path)
    (s.skills() / "mine").mkdir(parents=True)
    (s.skills() / "mine" / "SKILL.md").write_text("x")
    (s.home / ".orchestrator").mkdir()
    (s.home / ".orchestrator" / "bmad.json").write_text(json.dumps({"version": "1", "entries": {}}))
    credentials = s.home / ".claude" / ".credentials.json"
    credentials.write_bytes(b"secret-bytes")
    result = s.run("--reset", ORCH_SETUP_TRIGGER="")
    assert result.returncode == 0, result.stderr
    assert not (s.skills() / "mine").exists()
    assert credentials.read_bytes() == b"secret-bytes"
    assert s.record()["trigger"] == "reset"


def test_removed_deletes_the_recorded_bmad_entries(tmp_path: Path) -> None:
    s = _scratch(tmp_path)
    (s.client / "bmad.choice").write_text("removed\n")
    marker = s.root / "bmad-ran"
    (s.bmad / "install.sh").write_text(f"#!/usr/bin/env bash\ntouch {marker}\n")
    for harness in ("claude", "codex"):
        (s.skills(harness) / "bmad-a").mkdir(parents=True)
        (s.skills(harness) / "bmad-a" / "SKILL.md").write_text("x")
    (s.home / ".orchestrator").mkdir()
    bmad_json = s.home / ".orchestrator" / "bmad.json"
    bmad_json.write_text(
        json.dumps({"version": "1", "entries": {"claude": ["bmad-a"], "codex": ["bmad-a"]}})
    )
    result = s.run()
    assert result.returncode == 0, result.stderr
    for harness in ("claude", "codex"):
        assert not (s.skills(harness) / "bmad-a").exists()
    assert not bmad_json.exists()
    assert not marker.exists()
    assert s.record()["bmad"] == {"choice": "removed", "version": None, "ok": True}


def test_failing_bmad_script_is_recorded_and_the_run_continues(tmp_path: Path) -> None:
    s = _scratch(tmp_path)
    (s.bmad / "install.sh").write_text("#!/usr/bin/env bash\nexit 3\n")
    s.script("10-ok.sh", "exit 0")
    result = s.run()
    assert result.returncode == FAILED
    record = s.record()
    assert record["bmad"]["ok"] is False
    assert record["bmad"]["reason"] == "exit 3"
    assert record["scripts"][0]["ok"] is True
    SetupRun.model_validate(record)
