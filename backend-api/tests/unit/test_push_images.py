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


# ── the harness CLI pins reach the build ─────────────────────────────────────
#
# spec-harness-upgrade-survives-redeploy (2026-10-29): a published image carries the
# contract's pins, so they are read from `.env.example`; the operator's `.env` is never read.
# The script runs from a scratch copy of the repository root; `git` is shimmed for the
# revision label.

PINS = ("CLAUDE_CODE_VERSION", "CODEX_VERSION", "OPENCODE_VERSION")
#: values that are not pins and must never reach docker
OTHER_VALUES = ("ghp_dotenv_secret_never_in_argv", "sk-dotenv-litellm-never-in-argv")
CONTRACT = (
    f"GITHUB_TOKEN={OTHER_VALUES[0]}\n"
    f"LITELLM_API_KEY={OTHER_VALUES[1]}\n"
    "CLAUDE_CODE_VERSION=2.1.301  # raised for a fix\n"
    'CODEX_VERSION="0.201.0"\n'
    "OPENCODE_VERSION=1.21.0\n"
)


@pytest.fixture
def scratch_root(
    shim: tuple[Path, dict[str, str]], tmp_path: Path
) -> tuple[Path, Path, dict[str, str]]:
    log, env = shim
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(PUSH, root / "scripts" / "push-images.sh")
    git = tmp_path / "bin" / "git"
    git.write_text("#!/usr/bin/env bash\necho 0123456789abcdef\n")
    git.chmod(0o755)
    scrubbed = {k: v for k, v in env.items() if k not in PINS}
    return root, log, {**scrubbed, "PUSH": "0"}


def _run_in(root: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # fixed argv, no shell
        ["bash", str(root / "scripts" / "push-images.sh"), "9.9.9"],
        capture_output=True,
        text=True,
        cwd=root,
        env=env,
        check=False,
    )


def _builds(log: Path) -> list[str]:
    if not log.exists():
        return []
    return [call for call in log.read_text().splitlines() if call.startswith("buildx build")]


@needs_bash
def test_the_contract_pins_reach_every_build_and_nothing_else_of_it_does(
    scratch_root: tuple[Path, Path, dict[str, str]],
) -> None:
    root, log, env = scratch_root
    (root / ".env.example").write_text(CONTRACT)
    (root / ".env").write_text("CLAUDE_CODE_VERSION=7.7.7\nGITHUB_TOKEN=ghp_operator_dotenv\n")

    result = _run_in(root, env)

    assert result.returncode == 0, result.stdout + result.stderr
    builds = _builds(log)
    assert builds
    for build in builds:
        assert "--build-arg CLAUDE_CODE_VERSION=2.1.301 " in build
        assert "--build-arg CODEX_VERSION=0.201.0 " in build
        assert "--build-arg OPENCODE_VERSION=1.21.0 " in build
    logged = log.read_text() + result.stdout + result.stderr
    for value in (*OTHER_VALUES, "7.7.7", "ghp_operator_dotenv"):
        assert value not in logged


@needs_bash
def test_an_environment_pin_equal_to_the_contract_is_accepted(
    scratch_root: tuple[Path, Path, dict[str, str]],
) -> None:
    root, log, env = scratch_root
    (root / ".env.example").write_text(CONTRACT)

    result = _run_in(root, {**env, "OPENCODE_VERSION": "1.21.0"})

    assert result.returncode == 0, result.stdout + result.stderr
    for build in _builds(log):
        assert "--build-arg OPENCODE_VERSION=1.21.0 " in build


@needs_bash
def test_an_environment_pin_that_differs_from_the_contract_is_refused(
    scratch_root: tuple[Path, Path, dict[str, str]],
) -> None:
    root, log, env = scratch_root
    (root / ".env.example").write_text(CONTRACT)

    result = _run_in(root, {**env, "OPENCODE_VERSION": "1.22.0"})

    assert result.returncode != 0
    assert "OPENCODE_VERSION" in result.stderr
    assert "1.22.0" in result.stderr
    assert "1.21.0" in result.stderr
    assert _builds(log) == []


@needs_bash
def test_with_no_pin_anywhere_no_build_argument_is_passed(
    scratch_root: tuple[Path, Path, dict[str, str]],
) -> None:
    """The harness scripts' defaults then install, which equal `.env.example`."""
    root, log, env = scratch_root

    result = _run_in(root, env)

    assert result.returncode == 0, result.stdout + result.stderr
    for build in _builds(log):
        assert "--build-arg" not in build


@needs_bash
@pytest.mark.parametrize(
    "line",
    [
        "CLAUDE_CODE_VERSION=2.1.302 # one space before the comment",
        "CLAUDE_CODE_VERSION=2.1.302\t# a tab before the comment",
        'CLAUDE_CODE_VERSION="2.1.302"',
        "CLAUDE_CODE_VERSION='2.1.302'  # quoted, then a comment",
    ],
    ids=["one space", "tab", "double quotes", "single quotes and comment"],
)
def test_a_contract_pin_is_read_without_its_comment_or_quotes(
    scratch_root: tuple[Path, Path, dict[str, str]], line: str
) -> None:
    root, log, env = scratch_root
    (root / ".env.example").write_text(f"{line}\nCLAUDE_CODE_VERSION=9.9.9\n")

    result = _run_in(root, env)

    assert result.returncode == 0, result.stdout + result.stderr
    builds = _builds(log)
    assert builds
    for build in builds:
        assert "--build-arg CLAUDE_CODE_VERSION=2.1.302 " in build, "the first line wins"
        assert "#" not in build
        assert "'" not in build
        assert '"' not in build


@needs_bash
@pytest.mark.parametrize("source", ["env", "contract"])
@pytest.mark.parametrize("value", ["latest", "^2.1", "2.1", '"2.1.3'])
def test_a_pin_that_is_not_a_plain_version_stops_the_build(
    scratch_root: tuple[Path, Path, dict[str, str]], source: str, value: str
) -> None:
    root, log, env = scratch_root
    if source == "contract":
        (root / ".env.example").write_text(f"CODEX_VERSION={value}\n")
    else:
        env = {**env, "CODEX_VERSION": value}

    result = _run_in(root, env)

    assert result.returncode != 0
    assert "CODEX_VERSION" in result.stderr
    assert _builds(log) == []
