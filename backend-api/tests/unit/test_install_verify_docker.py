"""`deploy/install.sh` and the optional `docker` service (VERIFY_DOCKER, feat/docker-for-verify).

The sidecar is the compose profile `docker`. `.env`'s VERIFY_DOCKER is the one switch every
command reads, `--with-docker` / `--no-docker` on `install` and `start` write it, and the
script reconciles the stack to it:

- **On, every compose call names the profile**, so `pull`, `up`, `stop`, `logs` and `ps`
  reach the sidecar too; and the start proves backend-api reaches the daemon the way a Run
  does (`exec backend-api docker version`, through the agent's context). A sidecar left in
  the namespace of a backend-api that has since restarted answers nothing, so it is
  recreated once, and the start refuses if that does not fix it.
- **Off, a sidecar left from when it was on is removed** and its image cache kept.
- **`doctor` reports it without writing anything**: no `exec`, no `up` — container state and
  health through `ps` and `inspect` only, and a backend-api started after the sidecar is
  named, because that is the stale-namespace case.
- **An `.env` from an older release has no VERIFY_DOCKER line**, which means off; the flag
  appends it rather than refusing.

Same technique as `test_install_admin.py`: `docker` and `curl` shims on PATH, never the real
daemon (hard rule 9).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT, parse_env_example
from tests.unit.test_install_admin import CURL_SHIM, HARNESS_BODY, VERSION_BODY

DEPLOY_DIR = REPO_ROOT / "deploy"
PROFILE = "--profile docker"
RECREATE_SIDECAR = "up -d --no-deps --force-recreate --wait --wait-timeout 300 docker"
REACH = "exec -T backend-api docker version --format {{.Server.Version}}"
SIDECAR_ID = "sidecar0123"
BACKEND_ID = "backend0123"

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")

#: Records argv; answers the shapes the docker half of install.sh asks. `$SHIM_STATE` holds
#: one marker: the sidecar was force-recreated, after which the daemon answers when
#: `SHIM_REACH=after-recreate`.
DOCKER_SHIM = f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SHIM_DOCKER_LOG"
case "$*" in
\t"compose version") echo v2.99.0; exit 0 ;;
\t"compose version --short") echo 2.99.0; exit 0 ;;
\t"version --format"*) echo 28.0.0; exit 0 ;;
\tinfo*) exit 0 ;;
\t"inspect --format {{{{if .State.Health}}}}"*) echo "${{SHIM_HEALTH:-healthy}}"; exit 0 ;;
\t"inspect --format {{{{.State.StartedAt}}}} {SIDECAR_ID}") echo "$SHIM_SIDECAR_STARTED"; exit 0 ;;
\t"inspect --format {{{{.State.StartedAt}}}} {BACKEND_ID}") echo "$SHIM_BACKEND_STARTED"; exit 0 ;;
esac
case "$*" in
\t*"--force-recreate"*" docker") touch "$SHIM_STATE/recreated"; exit 0 ;;
\t*"exec -T backend-api docker version"*)
\t\tcase "${{SHIM_REACH:-yes}}" in
\t\t\tyes) echo 29.4.3; exit 0 ;;
\t\t\tafter-recreate) if [ -f "$SHIM_STATE/recreated" ]; then echo 29.4.3; exit 0; fi; exit 1 ;;
\t\t\t*) echo "Cannot connect to the Docker daemon" >&2; exit 1 ;;
\t\tesac ;;
\t*"ps --status running --services"*) printf '%s\\n' ${{SHIM_RUNNING:-}}; exit 0 ;;
\t*"ps -a --services"*) printf '%s\\n' ${{SHIM_ALL:-}}; exit 0 ;;
\t*"ps -q docker") echo {SIDECAR_ID}; exit 0 ;;
\t*"ps -q backend-api") echo {BACKEND_ID}; exit 0 ;;
esac
exit 0
"""


def _run(*args: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    dropped = {"GHCR_TOKEN", "GITHUB_TOKEN", "IMAGE_TAG", "DOCKER_CONFIG", "VERIFY_DOCKER"}
    clean = {k: v for k, v in os.environ.items() if k not in dropped}
    return subprocess.run(  # fixed argv, no shell
        ["bash", str(cwd / "install.sh"), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**clean, **env},
        check=False,
    )


@pytest.fixture
def installed(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """An extracted bundle with `.env` rendered and both shims on PATH; the stack 'runs'."""
    for name in ("install.sh", ".env.example", "docker-compose.yml"):
        shutil.copy(DEPLOY_DIR / name, tmp_path / name)
    (tmp_path / "VERSION").write_text("1.0.0-test\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", DOCKER_SHIM), ("curl", CURL_SHIM)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    state = tmp_path / "state"
    state.mkdir()
    (state / "version.json").write_text(json.dumps(VERSION_BODY))
    (state / "harnesses.json").write_text(json.dumps(HARNESS_BODY))
    (tmp_path / "dockercfg").mkdir()
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "SHIM_DOCKER_LOG": str(tmp_path / "docker.log"),
        "SHIM_CURL_LOG": str(tmp_path / "curl.log"),
        "SHIM_STATE": str(state),
        "SHIM_VERSION_FILE": str(state / "version.json"),
        "SHIM_HARNESS_FILE": str(state / "harnesses.json"),
        "DOCKER_CONFIG": str(tmp_path / "dockercfg"),
        "SHIM_RUNNING": "postgres backend-api web-client",
        "SHIM_SIDECAR_STARTED": "2026-11-02T10:00:05.5Z",
        "SHIM_BACKEND_STARTED": "2026-11-02T10:00:01.123456789Z",
        "GHCR_TOKEN": "ghp_verify_docker_test_0123456789",
    }
    result = _run("env", "--yes", cwd=tmp_path, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    (tmp_path / "docker.log").write_text("")
    return tmp_path, env


def calls(path: Path) -> list[str]:
    return (path / "docker.log").read_text().splitlines()


def switch(path: Path) -> str | None:
    return parse_env_example(path / ".env").get("VERIFY_DOCKER")


def set_switch(path: Path, value: str) -> None:
    lines = [
        f"VERIFY_DOCKER={value}" if line.startswith("VERIFY_DOCKER=") else line
        for line in (path / ".env").read_text().splitlines()
    ]
    (path / ".env").write_text("\n".join(lines) + "\n")


# ── the switch ───────────────────────────────────────────────────────────────


@needs_bash
def test_a_fresh_env_has_the_switch_off(installed: tuple[Path, dict[str, str]]) -> None:
    path, _env = installed

    assert switch(path) == "false"


@needs_bash
def test_with_docker_turns_it_on_and_every_compose_call_names_the_profile(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run("start", "--with-docker", "--no-platform", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert switch(path) == "true"
    compose_calls = [call for call in calls(path) if call.startswith("compose --project-directory")]
    assert compose_calls
    assert all(PROFILE in call for call in compose_calls), compose_calls
    assert any(call.endswith(REACH) for call in compose_calls), compose_calls
    assert "daemon 29.4.3 answers backend-api" in result.stdout
    assert "§ Trust" in result.stdout


@needs_bash
def test_with_docker_appends_the_switch_to_an_env_that_predates_it(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    kept = [
        line
        for line in (path / ".env").read_text().splitlines()
        if not line.startswith("VERIFY_DOCKER=")
    ]
    (path / ".env").write_text("\n".join(kept) + "\n")

    result = _run("start", "--with-docker", "--no-platform", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert switch(path) == "true"


@needs_bash
def test_off_by_default_names_no_profile_and_asks_no_daemon(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run("start", "--no-platform", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    driving = [
        call
        for call in calls(path)
        if call.startswith("compose --project-directory") and " ps " not in call
    ]
    assert driving
    assert not any(PROFILE in call for call in driving), driving
    assert not any(" exec " in call for call in calls(path))


@needs_bash
@pytest.mark.parametrize("command", ["doctor", "stop", "upgrade", "harness"])
def test_the_flag_belongs_to_install_and_start_only(
    installed: tuple[Path, dict[str, str]], command: str
) -> None:
    path, env = installed

    result = _run(command, "--with-docker", cwd=path, env=env)

    assert result.returncode != 0
    assert "--with-docker / --no-docker are for install and start" in result.stderr
    assert switch(path) == "false"


# ── reconciling the stack to the switch ──────────────────────────────────────


@needs_bash
def test_a_sidecar_backend_api_cannot_reach_is_recreated_once(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run(
        "start",
        "--with-docker",
        "--no-platform",
        cwd=path,
        env={**env, "SHIM_REACH": "after-recreate"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    recreates = [call for call in calls(path) if call.endswith(RECREATE_SIDECAR)]
    assert len(recreates) == 1, calls(path)
    assert "recreating it in backend-api's network namespace" in result.stdout


@needs_bash
def test_a_sidecar_that_stays_unreachable_refuses_the_start(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run(
        "start", "--with-docker", "--no-platform", cwd=path, env={**env, "SHIM_REACH": "no"}
    )

    assert result.returncode != 0
    assert "still cannot reach the docker service" in result.stderr
    assert "./install.sh logs" in result.stderr


@needs_bash
def test_no_docker_turns_it_off_and_removes_a_leftover_sidecar(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    set_switch(path, "true")

    result = _run(
        "start",
        "--no-docker",
        "--no-platform",
        cwd=path,
        env={**env, "SHIM_ALL": "postgres backend-api web-client docker"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert switch(path) == "false"
    assert any(call.endswith(f"{PROFILE} rm -sf docker") for call in calls(path)), calls(path)
    assert "docker-data volume is kept" in result.stdout
    assert not any("down" in call for call in calls(path))


@needs_bash
def test_off_with_no_sidecar_removes_nothing(installed: tuple[Path, dict[str, str]]) -> None:
    path, env = installed

    _run("start", "--no-platform", cwd=path, env=env)

    assert not any(" rm " in call for call in calls(path))


@needs_bash
def test_uninstall_reaches_the_sidecar_and_its_volume_even_when_off(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run("uninstall", "--yes", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert any(call.endswith(f"{PROFILE} down -v --remove-orphans") for call in calls(path))


@needs_bash
def test_diagnose_prints_the_switch_unmasked(installed: tuple[Path, dict[str, str]]) -> None:
    """A flag, not a secret: a maintainer needs to see it."""
    path, env = installed
    set_switch(path, "true")

    result = _run("diagnose", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    report = next((path / "diagnostics").glob("*.md")).read_text()
    assert "VERIFY_DOCKER=true" in report


# ── doctor ───────────────────────────────────────────────────────────────────


def dind_line(output: str) -> str:
    found = [line for line in output.splitlines() if "  dind  " in line]
    assert len(found) == 1, output
    return found[0]


def doctor(path: Path, env: dict[str, str], **extra: str) -> subprocess.CompletedProcess[str]:
    result = _run("doctor", cwd=path, env={**env, **extra})
    for forbidden in (" pull", " up ", " restart", " stop", " down", " exec ", " rm "):
        assert not any(forbidden in call for call in calls(path)), (forbidden, calls(path))
    return result


@needs_bash
def test_doctor_off_is_ok_and_names_the_flag(installed: tuple[Path, dict[str, str]]) -> None:
    path, env = installed

    result = doctor(path, env)

    line = dind_line(result.stdout)
    assert line.startswith("ok")
    assert "Cannot connect to the Docker daemon" in line
    assert "./install.sh start --with-docker" in line


@needs_bash
def test_doctor_off_with_a_running_sidecar_warns(installed: tuple[Path, dict[str, str]]) -> None:
    path, env = installed

    result = doctor(path, env, SHIM_RUNNING="postgres backend-api web-client docker")

    assert dind_line(result.stdout).startswith("warn")


@needs_bash
def test_doctor_on_and_healthy_is_ok(installed: tuple[Path, dict[str, str]]) -> None:
    path, env = installed
    set_switch(path, "true")

    result = doctor(path, env, SHIM_RUNNING="postgres backend-api web-client docker")

    assert dind_line(result.stdout).startswith("ok"), result.stdout


@needs_bash
@pytest.mark.parametrize(
    ("extra", "names"),
    [
        ({"SHIM_RUNNING": "postgres backend-api web-client"}, "not running"),
        (
            {"SHIM_RUNNING": "postgres backend-api web-client docker", "SHIM_HEALTH": "unhealthy"},
            "unhealthy",
        ),
        (
            {
                "SHIM_RUNNING": "postgres backend-api web-client docker",
                "SHIM_BACKEND_STARTED": "2026-11-02T11:00:00Z",
            },
            "old network namespace",
        ),
    ],
)
def test_doctor_on_fails_naming_the_case_and_the_fix(
    installed: tuple[Path, dict[str, str]], extra: dict[str, str], names: str
) -> None:
    path, env = installed
    set_switch(path, "true")

    result = doctor(path, env, **extra)

    line = dind_line(result.stdout)
    assert line.startswith("fail"), line
    assert names in line
    assert "./install.sh start" in line
    assert result.returncode != 0
