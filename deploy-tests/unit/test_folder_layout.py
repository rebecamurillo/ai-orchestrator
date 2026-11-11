"""The client folder layout and the product manifest (epic 3 story 1, SPEC CAP-1).

`scripts/product_manifest.py` names the product files; the archive (`kit bootstrap`, `make
bundle`) carries them; `deploy/.gitignore` keeps the client's files out of a repository; and
`setup/examples/copy-folder.sh` is the example a client copies into `setup/`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

DEPLOY = REPO_ROOT / "deploy"
GENERATOR = REPO_ROOT / "scripts" / "product_manifest.py"
ENTRYPOINT = REPO_ROOT / "backend-api" / "docker-entrypoint.sh"
COPY_FOLDER = DEPLOY / "setup" / "examples" / "copy-folder.sh"

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _manifest(deploy: Path, version: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "-I", str(GENERATOR), str(deploy), str(version)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scratch_root(tmp_path: Path) -> Path:
    """An `/app`-like root: the repository's deploy/ plus what the image build adds."""
    root = tmp_path / "app"
    shutil.copytree(DEPLOY, root / "deploy")
    shipped = root / "deploy" / "templates" / "shipped"
    shipped.mkdir(parents=True)
    for template in (REPO_ROOT / "templates").glob("*.yaml"):
        shutil.copy2(template, shipped / template.name)
    (root / "VERSION").write_text("1.2.3\n")
    manifest = _manifest(root / "deploy", root / "VERSION")
    (root / "deploy" / "product-files.json").write_text(json.dumps(manifest))
    return root


# ── AC1: the generator ───────────────────────────────────────────────────────


def test_the_manifest_names_every_product_file_and_the_two_seeds() -> None:
    manifest = _manifest(DEPLOY, REPO_ROOT / "VERSION")

    assert manifest["release"] == (REPO_ROOT / "VERSION").read_text().strip()
    entries = {entry["path"]: entry for entry in manifest["files"]}
    assert [e["path"] for e in manifest["files"]] == sorted(entries)
    assert {p for p, e in entries.items() if e["role"] == "seed"} == {
        "compose.override.yml",
        "setup/bmad.choice",
    }
    assert {e["role"] for e in entries.values()} == {"seed", "product"}
    assert "VERSION" in entries
    assert entries["VERSION"]["sha256"] == _sha(REPO_ROOT / "VERSION")
    for path, entry in entries.items():
        if path != "VERSION":
            assert entry["sha256"] == _sha(DEPLOY / path), path
    assert not any(p.startswith("llm-platform/") for p in entries)
    on_disk = {
        p.relative_to(DEPLOY).as_posix()
        for p in DEPLOY.rglob("*")
        if p.is_file() and p.relative_to(DEPLOY).parts[0] != "llm-platform"
    }
    assert on_disk <= set(entries)


# ── AC2: the archive `kit bootstrap` builds ──────────────────────────────────


def _bootstrap_argv(root: Path) -> list[str]:
    line = next(
        ln for ln in ENTRYPOINT.read_text().splitlines() if ln.strip().startswith("bootstrap)")
    )
    command = line.split("exec ", 1)[1].split(" ;;", 1)[0]
    return [part.replace("/app", str(root)) for part in shlex.split(command)]


def _gnu_tar() -> bool:
    if shutil.which("tar") is None:
        return False
    out = subprocess.run(["tar", "--version"], capture_output=True, text=True, check=False)
    return "GNU tar" in out.stdout


@pytest.mark.skipif(not _gnu_tar(), reason="GNU tar not available")
def test_the_bootstrap_archive_holds_the_folder_layout_and_no_llm_platform(tmp_path: Path) -> None:
    root = _scratch_root(tmp_path)
    argv = _bootstrap_argv(root)
    archive = tmp_path / "out.tar"
    with archive.open("wb") as fh:
        result = subprocess.run(argv, stdout=fh, stderr=subprocess.PIPE, check=False)
    assert result.returncode == 0, result.stderr

    with tarfile.open(archive) as tar:
        names = {m.name.rstrip("/") for m in tar.getmembers()}
    base = "ai-orchestrator/"
    for path in (
        "README.md",
        "VERSION",
        "install.sh",
        "docker-compose.yml",
        "release.env",
        ".env.example",
        ".gitignore",
        "product-files.json",
        "compose.override.yml",
        "kit",
        "bmad/install.sh",
        "bmad/README.md",
        "setup/README.md",
        "setup/examples/copy-folder.sh",
        "setup/bmad.choice",
        "templates/README.md",
    ):
        assert base + path in names, path
    shipped = {n for n in names if n.startswith(base + "templates/shipped/")}
    assert shipped == {
        base + "templates/shipped/" + t.name for t in (REPO_ROOT / "templates").glob("*.yaml")
    }
    assert not [n for n in names if n.startswith(base + "llm-platform")]


# ── AC3: the product .gitignore ──────────────────────────────────────────────


@needs_git
def test_the_gitignore_ignores_the_clients_files_and_nothing_else(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()
    shutil.copy2(DEPLOY / ".gitignore", folder / ".gitignore")
    subprocess.run(["git", "init", "-q"], cwd=folder, check=True)

    def ignored(path: str) -> bool:
        return (
            subprocess.run(
                ["git", "check-ignore", "--no-index", "-q", path], cwd=folder, check=False
            ).returncode
            == 0
        )

    for path in (
        ".env",
        "setup/assets/x/.env",
        "backups/a.dump",
        "logs/setup/x.log",
        "diagnostics/r.md",
        ".upgrade/1/staged/VERSION",
    ):
        assert ignored(path), path
    for path in ("templates/x.yaml", "setup/10-copy-folder.sh", "compose.override.yml"):
        assert not ignored(path), path


# ── AC4, AC5: copy-folder.sh ─────────────────────────────────────────────────


def _install_copy_folder(folder: Path) -> Path:
    (folder / "setup").mkdir(parents=True)
    script = folder / "setup" / "10-copy-folder.sh"
    shutil.copy2(COPY_FOLDER, script)
    script.chmod(0o755)
    return script


def _run_copy_folder(script: Path, home: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, env=env, check=False
    )


@needs_bash
def test_copy_folder_copies_and_removes_only_what_it_copied(tmp_path: Path) -> None:
    folder, home = tmp_path / "folder", tmp_path / "home"
    home.mkdir()
    script = _install_copy_folder(folder)
    assets = folder / "setup" / "assets"
    for rel in ("claude/.claude/skills/a", "claude/.claude/skills/b", "codex/.agents/skills/c"):
        (assets / rel).mkdir(parents=True)
        (assets / rel / "SKILL.md").write_text(rel)
    foreign = home / ".claude" / "skills" / "mine"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("client")

    first = _run_copy_folder(script, home)
    assert first.returncode == 0, first.stderr
    assert (home / ".claude/skills/a/SKILL.md").read_text() == "claude/.claude/skills/a"
    assert (home / ".claude/skills/b/SKILL.md").is_file()
    assert (home / ".agents/skills/c/SKILL.md").read_text() == "codex/.agents/skills/c"
    listed = (home / ".claude/skills/.copy-folder-installed").read_text().split()
    assert sorted(listed) == ["a", "b"]
    assert (home / ".agents/skills/.copy-folder-installed").read_text().split() == ["c"]

    shutil.rmtree(assets / "claude/.claude/skills/b")
    second = _run_copy_folder(script, home)
    assert second.returncode == 0, second.stderr
    assert not (home / ".claude/skills/b").exists()
    assert (home / ".claude/skills/a/SKILL.md").is_file()
    assert (foreign / "SKILL.md").read_text() == "client"
    assert (home / ".claude/skills/.copy-folder-installed").read_text().split() == ["a"]


@needs_bash
def test_copy_folder_without_assets_exits_one_and_writes_nothing(tmp_path: Path) -> None:
    folder, home = tmp_path / "folder", tmp_path / "home"
    home.mkdir()
    script = _install_copy_folder(folder)

    result = _run_copy_folder(script, home)

    assert result.returncode == 1
    assert result.stderr.strip()
    assert list(home.iterdir()) == []


def test_the_example_is_executable_and_the_asset_lists_follow_the_harness_scripts() -> None:
    assert os.access(COPY_FOLDER, os.X_OK)
    text = COPY_FOLDER.read_text()
    for harness in ("claude", "codex", "opencode"):
        declared = re.search(
            r"^ASSET_DIRS=\((.*)\)", (REPO_ROOT / "scripts/harness" / f"{harness}.sh").read_text(), re.M
        )
        assert declared is not None
        for directory in declared.group(1).split():
            assert directory in text, (harness, directory)
