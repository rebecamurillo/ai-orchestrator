"""`readiness_fixture.sh` installs BMAD from `BMAD_PREFIX` when present, else `npx` (CAP-2)."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "readiness_fixture.sh"
ARGS = "install --yes --modules bmm --tools claude-code,codex,opencode --directory"


@pytest.fixture(autouse=True)
def git_binary() -> str:
    found = shutil.which("git")
    if found is None:
        pytest.fail("git is not on PATH: this module drives real `git`")
    return found


def _installer(path: Path, log: Path, label: str) -> None:
    """A stub that logs its argv and writes one file into `--directory`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "{label} $*" >> "{log}"\n'
        'dir=""; while [ $# -gt 0 ]; do [ "$1" = --directory ] && dir="$2"; shift; done\n'
        'echo x > "$dir/installed.txt"\n'
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run(tmp_path: Path, *, with_prefix_bin: bool) -> list[str]:
    bin_dir = tmp_path / "bin"
    prefix = tmp_path / "bmad"
    log = tmp_path / "calls.log"
    src = tmp_path / "src"
    src.mkdir()
    (src / "README.md").write_text("fixture\n")
    _installer(bin_dir / "npx", log, "npx")
    if with_prefix_bin:
        _installer(prefix / "bin" / "bmad-method", log, "prefix")
    scratch = tmp_path / "work" / "readiness" / "scratch"
    result = subprocess.run(  # fixed argv, no shell
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "WORK_DIR": str(tmp_path / "work"),
            "READINESS_FIXTURE_SRC": str(src),
            "BMAD_PREFIX": str(prefix),
            "BMAD_VERSION": "9.9.9",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        },
    )
    assert result.returncode == 0, result.stderr
    return [re.sub(re.escape(str(scratch)), "<scratch>", ln) for ln in log.read_text().splitlines()]


def test_the_prefix_installer_runs_and_npx_does_not(tmp_path: Path) -> None:
    assert _run(tmp_path, with_prefix_bin=True) == [f"prefix {ARGS} <scratch>"]


def test_without_the_prefix_installer_npx_runs_with_the_pinned_version(tmp_path: Path) -> None:
    assert _run(tmp_path, with_prefix_bin=False) == [
        f"npx --yes bmad-method@9.9.9 {ARGS} <scratch>"
    ]
