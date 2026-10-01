"""`scripts/push-images.sh` — the manual publish, driven against a docker shim.

Nothing here builds or pushes: the shim records every docker invocation and answers success,
so what is proved is the control flow around the build — that a token in the environment
becomes a `docker login … --password-stdin` before anything is built, that it is never
printed, and that `PUSH=0` neither logs in nor pushes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

PUSH = REPO_ROOT / "scripts" / "push-images.sh"
TOKEN = "ghp_test_token_value"

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")


@pytest.fixture
def shim(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """A docker that records its argv (and stdin, for `login`) and succeeds."""
    log = tmp_path / "docker.log"
    stdin_log = tmp_path / "stdin.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(
        "#!/usr/bin/env bash\n"
        f'printf \'%s\\n\' "$*" >> "{log}"\n'
        f'[[ "$1" == "login" ]] && cat >> "{stdin_log}"\n'
        '[[ "$1 $2" == "version --format" ]] && echo linux/arm64\n'
        "exit 0\n"
    )
    (bin_dir / "docker").chmod(0o755)
    # no network: the user lookup must fall back rather than hang or fail
    (bin_dir / "curl").write_text("#!/usr/bin/env bash\nexit 1\n")
    (bin_dir / "curl").chmod(0o755)
    clean = {k: v for k, v in os.environ.items() if k not in {"GHCR_TOKEN", "GITHUB_TOKEN"}}
    env = {**clean, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    return log, env


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # fixed argv, no shell
        ["bash", str(PUSH), "9.9.9"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        check=False,
    )


@needs_bash
def test_a_token_in_the_environment_logs_in_before_the_first_build(
    shim: tuple[Path, dict[str, str]],
) -> None:
    log, env = shim

    result = _run({**env, "GHCR_TOKEN": TOKEN, "GITHUB_USER": "someone"})

    assert result.returncode == 0, result.stdout + result.stderr
    calls = log.read_text().splitlines()
    login = next(i for i, call in enumerate(calls) if call.startswith("login ghcr.io"))
    build = next(i for i, call in enumerate(calls) if call.startswith("buildx build"))
    assert login < build
    assert "-u someone --password-stdin" in calls[login]
    assert (log.parent / "stdin.log").read_text() == TOKEN


@needs_bash
def test_the_token_never_appears_in_argv_or_output(shim: tuple[Path, dict[str, str]]) -> None:
    log, env = shim

    result = _run({**env, "GHCR_TOKEN": TOKEN})

    assert TOKEN not in log.read_text()
    assert TOKEN not in result.stdout + result.stderr


@needs_bash
def test_without_a_token_the_daemon_is_assumed_logged_in(shim: tuple[Path, dict[str, str]]) -> None:
    log, env = shim

    result = _run(env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not any(call.startswith("login") for call in log.read_text().splitlines())


@needs_bash
def test_build_only_neither_logs_in_nor_pushes(shim: tuple[Path, dict[str, str]]) -> None:
    log, env = shim

    result = _run({**env, "GHCR_TOKEN": TOKEN, "PUSH": "0"})

    assert result.returncode == 0, result.stdout + result.stderr
    calls = log.read_text()
    assert "login" not in calls
    assert "--push" not in calls
    assert "--load" in calls
