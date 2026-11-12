"""BMAD leaves the harness homes (epic 2 story 2, SPEC CAP-2; AD-16 as amended).

The image carries `bmad-method` only as a package under `/opt/bmad`; no `install` verb puts a
`bmad-*` folder into a harness home, `asset-dirs` names the folders each harness reads, and
`doctor` reads the skill catalog instead of looking for one BMAD skill. Every script is driven
with `subprocess` against stub `npm`, `npx` and CLI executables on a scratch `PATH`.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

HARNESS_DIR = REPO_ROOT / "scripts" / "harness"
HARNESSES = ("claude", "codex", "opencode")

#: `asset-dirs` per harness, in the order the script declares them.
CLAUDE_DIRS = [".claude/skills", ".claude/agents", ".claude/commands"]
CODEX_DIRS = [".agents/skills", ".codex/prompts"]
OPENCODE_DIR_COUNT = 3
OPERATOR_SKILL = "operator-skill"

VERSION_LINE = {
    "claude": "2.1.319 (Claude Code)",
    "codex": "codex-cli 0.167.0",
    "opencode": "1.19.5",
}


def _stub(path: Path, body: str) -> None:
    path.write_text(f"#!/usr/bin/env bash\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def sandbox(tmp_path: Path) -> dict[str, Path]:
    """Scratch AGENT_HOME, image prefix, operator skills and a bin of logging stubs."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    _stub(bin_dir / "npm", f'echo "npm $*" >> "{log}"')
    _stub(bin_dir / "npx", f'echo "npx $*" >> "{log}"')
    for name, line in VERSION_LINE.items():
        _stub(bin_dir / name, f'echo "{line}"')
    skills = tmp_path / "operator" / OPERATOR_SKILL
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("# operator\n")
    home = tmp_path / "home"
    home.mkdir()
    return {
        "bin": bin_dir,
        "log": log,
        "home": home,
        "prefix": tmp_path / "image",
        "operator": tmp_path / "operator",
    }


def _run(
    sandbox: dict[str, Path], name: str, verb: str, **extra: str
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{sandbox['bin']}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(sandbox["home"]),
        "AGENT_HOME": str(sandbox["home"]),
        "HARNESS_IMAGE_PREFIX": str(sandbox["prefix"]),
        "OPERATOR_SKILLS_SRC": str(sandbox["operator"]),
        **extra,
    }
    return subprocess.run(  # fixed argv, no shell
        ["bash", str(HARNESS_DIR / f"{name}.sh"), verb],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _asset_dirs(name: str) -> list[str]:
    env = {"PATH": os.environ["PATH"]}
    result = subprocess.run(  # fixed argv, no shell
        ["bash", str(HARNESS_DIR / f"{name}.sh"), "asset-dirs"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


@pytest.mark.parametrize("name", HARNESSES)
def test_install_puts_the_operator_skill_and_no_bmad_folder_in_the_harness_home(
    sandbox: dict[str, Path], name: str
) -> None:
    result = _run(sandbox, name, "install")

    assert result.returncode == 0, result.stderr
    calls = sandbox["log"].read_text()
    assert "npx" not in calls
    skills = sandbox["home"] / _asset_dirs(name)[0]
    assert sorted(p.name for p in skills.iterdir()) == [OPERATOR_SKILL]
    assert not list(skills.glob("bmad-*"))
    manifest = json.loads((skills.parent / "skills-manifest.json").read_text())
    assert manifest == {"skills": [OPERATOR_SKILL]}


def test_asset_dirs_name_each_harnesss_folders_with_only_path_in_the_environment() -> None:
    assert _asset_dirs("claude") == CLAUDE_DIRS
    assert _asset_dirs("codex") == CODEX_DIRS
    opencode = _asset_dirs("opencode")
    assert opencode[0] == ".config/opencode/skills"
    assert len(opencode) == OPENCODE_DIR_COUNT
    assert all(d.startswith(".config/opencode/") for d in opencode)


@pytest.mark.parametrize("name", HARNESSES)
def test_configure_creates_every_asset_dir_with_both_services_disabled(
    sandbox: dict[str, Path], name: str
) -> None:
    result = _run(sandbox, name, "configure", LITELLM_BASE_URL="", LANGFUSE_BASE_URL="")

    assert result.returncode == 0, result.stderr
    for relative in _asset_dirs(name):
        assert (sandbox["home"] / relative).is_dir(), relative


def _doctor(sandbox: dict[str, Path], name: str) -> subprocess.CompletedProcess[str]:
    return _run(sandbox, name, "doctor", LITELLM_BASE_URL="", LANGFUSE_BASE_URL="")


@pytest.mark.parametrize("name", HARNESSES)
def test_doctor_fails_naming_the_manifest_when_it_is_missing(
    sandbox: dict[str, Path], name: str
) -> None:
    _run(sandbox, name, "configure", LITELLM_BASE_URL="", LANGFUSE_BASE_URL="")
    manifest = sandbox["home"] / _asset_dirs(name)[0]
    manifest = manifest.parent / "skills-manifest.json"

    result = _doctor(sandbox, name)

    assert result.returncode != 0
    assert str(manifest) in result.stderr


@pytest.mark.parametrize("name", HARNESSES)
def test_doctor_passes_on_a_valid_empty_manifest_without_bmad_build_auto(
    sandbox: dict[str, Path], name: str
) -> None:
    _run(sandbox, name, "configure", LITELLM_BASE_URL="", LANGFUSE_BASE_URL="")
    skills = sandbox["home"] / _asset_dirs(name)[0]
    (skills.parent / "skills-manifest.json").write_text('{"skills":[]}\n')
    assert not (skills / "bmad-build-auto").exists()

    result = _doctor(sandbox, name)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", HARNESSES)
def test_doctor_fails_on_a_manifest_that_is_not_json(sandbox: dict[str, Path], name: str) -> None:
    _run(sandbox, name, "configure", LITELLM_BASE_URL="", LANGFUSE_BASE_URL="")
    skills = sandbox["home"] / _asset_dirs(name)[0]
    (skills.parent / "skills-manifest.json").write_text("not json")

    assert _doctor(sandbox, name).returncode != 0


def test_install_bmad_package_runs_one_bounded_free_npm_install_at_the_default_version(
    tmp_path: Path, sandbox: dict[str, Path]
) -> None:
    common = (HARNESS_DIR / "_common.sh").read_text()
    match = re.search(r"\$\{BMAD_VERSION:=([^}]+)\}", common)
    assert match is not None
    prefix = tmp_path / "bmad"
    script = f'source "{HARNESS_DIR}/_common.sh"; install_bmad_package'

    result = subprocess.run(  # fixed argv, no shell
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{sandbox['bin']}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(sandbox["home"]),
            "BMAD_PREFIX": str(prefix),
        },
    )

    assert result.returncode == 0, result.stderr
    assert sandbox["log"].read_text().splitlines() == [
        f"npm install -g --prefix {prefix} --fetch-retries=0 --fetch-timeout=60000 "
        f"bmad-method@{match.group(1)}"
    ]
