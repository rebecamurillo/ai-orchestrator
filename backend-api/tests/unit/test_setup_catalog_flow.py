"""After a setup run, backend-api's skill catalog lists what the skills folders hold (epic 5).

The pieces epic 5 wires together are each tested alone: `prepare.sh` creates the mounted
folders, the harness `catalog` verb writes a manifest, `FsSkillCatalog` reads one. This module
chains them on one agent home: prepare, change the skills folders the way `bmad install|remove`
does, run `catalog`, read with the reader pre-flight uses. It also holds the names the chain
depends on in agreement: the skills folder each harness declares, the manifest the reader looks
for, the harness lists of `prepare.sh`, `run.sh` and `install.sh`, and the image paths
`install.sh` calls. `deploy/install.sh` is read as text, never run (SPEC § Constraints).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator.infrastructure.skill_catalog import MANIFESTS, FsSkillCatalog
from tests.unit.conftest import REPO_ROOT

HARNESS_DIR = REPO_ROOT / "scripts" / "harness"
PREPARE = REPO_ROOT / "scripts" / "setup" / "prepare.sh"
RUN_SH = REPO_ROOT / "scripts" / "setup" / "run.sh"
INSTALL_SH = REPO_ROOT / "deploy" / "install.sh"
DOCKERFILE = REPO_ROOT / "backend-api" / "Dockerfile"
HARNESSES = ("claude", "codex", "opencode")
BASH = shutil.which("bash") or "bash"


def _env(home: Path) -> dict[str, str]:
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "AGENT_HOME": str(home),
        "HARNESS_SCRIPTS_DIR": str(HARNESS_DIR),
    }


def _sh(home: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [BASH, *argv], env=_env(home), capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def _skills_folder(harness: str) -> str:
    out = subprocess.run(
        [BASH, str(HARNESS_DIR / f"{harness}.sh"), "asset-dirs"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    folders = [line for line in out if Path(line).name == "skills"]
    assert len(folders) == 1, out
    return folders[0]


def _catalog(home: Path, harness: str) -> None:
    _sh(home, str(HARNESS_DIR / f"{harness}.sh"), "catalog")


def _setup_service_run() -> str:
    text = INSTALL_SH.read_text()
    match = re.search(r"^setup_service_run\(\) \{.*?^\}", text, re.MULTILINE | re.DOTALL)
    assert match, "setup_service_run not found in deploy/install.sh"
    return match.group(0)


# ── the chain on one agent home ──


@pytest.mark.parametrize("harness", HARNESSES)
def test_a_fresh_home_has_an_empty_catalog_not_an_unavailable_one(
    tmp_path: Path, harness: str
) -> None:
    _sh(tmp_path, str(PREPARE))
    _catalog(tmp_path, harness)

    assert FsSkillCatalog(tmp_path).installed_skills(harness) == frozenset()


@pytest.mark.parametrize("harness", HARNESSES)
def test_installed_then_removed_skills_reach_the_reader_without_a_new_reader(
    tmp_path: Path, harness: str
) -> None:
    _sh(tmp_path, str(PREPARE))
    skills = tmp_path / _skills_folder(harness)
    reader = FsSkillCatalog(tmp_path)
    for name in ("bmad-build", "bmad-review", "own-skill"):
        (skills / name).mkdir()
    (skills / "README.md").write_text("not a skill")

    _catalog(tmp_path, harness)
    assert reader.installed_skills(harness) == {"bmad-build", "bmad-review", "own-skill"}

    shutil.rmtree(skills / "bmad-review")
    _catalog(tmp_path, harness)
    assert reader.installed_skills(harness) == {"bmad-build", "own-skill"}


def test_the_opencode_catalog_is_the_local_harness_catalog(tmp_path: Path) -> None:
    _sh(tmp_path, str(PREPARE))
    (tmp_path / _skills_folder("opencode") / "bmad-build").mkdir()

    _catalog(tmp_path, "opencode")

    assert FsSkillCatalog(tmp_path).installed_skills("local") == {"bmad-build"}


def test_a_catalog_run_touches_only_its_own_harness(tmp_path: Path) -> None:
    _sh(tmp_path, str(PREPARE))
    for harness in HARNESSES:
        (tmp_path / _skills_folder(harness) / f"only-{harness}").mkdir()

    _catalog(tmp_path, "codex")

    reader = FsSkillCatalog(tmp_path)
    assert reader.installed_skills("codex") == {"only-codex"}
    assert reader.installed_skills("claude") is None
    assert reader.installed_skills("opencode") is None


# ── the names the chain depends on agree ──


@pytest.mark.parametrize("harness", HARNESSES)
def test_the_declared_skills_folder_sits_beside_the_manifest_the_reader_reads(
    harness: str,
) -> None:
    assert Path(_skills_folder(harness)).parent / "skills-manifest.json" == MANIFESTS[harness]


def test_prepare_run_and_install_name_the_same_harnesses() -> None:
    loop = "for h in claude codex opencode; do"
    assert loop in PREPARE.read_text()
    assert "HARNESSES=(claude codex opencode)" in RUN_SH.read_text()
    assert loop in _setup_service_run()
    assert {name for name in MANIFESTS if name != "local"} == set(HARNESSES)


def test_install_calls_catalog_and_prepare_at_paths_the_image_ships() -> None:
    body = _setup_service_run()
    dockerfile = DOCKERFILE.read_text()

    assert '"/app/scripts/harness/${h}.sh" catalog' in body
    assert "COPY --chown=agent:agent scripts/harness /app/scripts/harness" in dockerfile
    for harness in HARNESSES:
        assert re.search(r"^\s*catalog\)", (HARNESS_DIR / f"{harness}.sh").read_text(), re.M)

    assert "--entrypoint /app/scripts/setup/prepare.sh backend-api" in body
    assert "COPY --chown=agent:agent scripts/setup /app/scripts/setup" in dockerfile
    assert os.access(PREPARE, os.X_OK)


def test_install_refreshes_the_catalog_after_the_setup_service_and_never_restarts() -> None:
    body = _setup_service_run()

    assert body.index("prepare.sh") < body.index(" setup ${1+") < body.index("catalog")
    assert not re.search(r"\b(restart|stop|down)\b", body.replace("--rm", ""))


def test_run_sh_phase_four_counts_and_writes_no_manifest() -> None:
    text = RUN_SH.read_text()
    phase_four = text[text.index("declare -A COUNT=()") :]

    assert "write_skills_manifest" not in phase_four
    assert "-mindepth 1 -maxdepth 1 -type d" in phase_four
