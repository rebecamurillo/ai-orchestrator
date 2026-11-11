"""`deploy/install.sh install` on the folder — the gateway and tracing given, no platform.

Epic 3 story 2 (2026-11-11): the LLM platform leaves the product; `install` takes the six
gateway and tracing values from the environment or asks for them, writes only what is absent,
installs BMAD unless `--no-bmad`, and runs the setup service under the instance hold. Docker
and curl are shims on PATH, as in `test_deploy_install.py`; nothing here touches a daemon.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT, parse_env_example

DEPLOY_DIR = REPO_ROOT / "deploy"
INSTALL = DEPLOY_DIR / "install.sh"
TAG = "1.0.0-test"
SECRET = "sk-never-printed-0123456789"
SIX = (
    "LITELLM_BASE_URL",
    "LITELLM_API_KEY",
    "LITELLM_SPEND_KEY",
    "LANGFUSE_BASE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
)
BMAD_PIN = next(
    line.split("=", 1)[1]
    for line in (DEPLOY_DIR / "release.env").read_text().splitlines()
    if line.startswith("BMAD_VERSION=")
)

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")

DOCKER_SHIM = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SHIM_DOCKER_LOG"
case "$*" in
\t"compose version") echo v2.99.0; exit 0 ;;
\t"compose version --short") echo 2.99.0; exit 0 ;;
\t"version --format"*) echo "${SHIM_ENGINE:-28.0.0}"; exit 0 ;;
\t"info --format"*) printf '%s\\n' "${SHIM_DOCKER_ROOT:-}"; exit 0 ;;
\tinfo) exit 0 ;;
\t"image inspect"*) exit 0 ;;
\t"system df"*) echo "Images 1.1GB reclaimable 0B"; exit 0 ;;
esac
case "$*" in
\t*" run --rm "*" setup") exit "${SHIM_SETUP_RC:-0}" ;;
\t*"ps --status running --services"*) printf '%s\\n' ${SHIM_RUNNING:-}; exit 0 ;;
\t*" ps") echo "NAME STATUS"; exit 0 ;;
esac
exit 0
"""

CURL_SHIM = """#!/usr/bin/env bash
method=GET; body=""; out=""; url=""; prev=""
for arg in "$@"; do
\tcase "$prev" in -X) method="$arg" ;; -d) body="$arg" ;; -o) out="$arg" ;; esac
\tcase "$arg" in http*) url="$arg" ;; esac
\tprev="$arg"
done
printf '%s %s %s\\n' "$method" "$url" "$body" >> "$SHIM_CURL_LOG"
printf '%s\\n' "$*" >> "$SHIM_CURL_ARGV"
emit() {
\tif [ -n "$out" ] && [ "$out" != "/dev/null" ] && [ -n "$2" ]; then cp "$2" "$out"; fi
\tprintf '%s' "$1"
\texit 0
}
case "$url" in
\t*/api/v1/instance/hold) emit "${SHIM_HOLD_CODE:-200}" "" ;;
\t*/healthz) emit 200 "" ;;
\t*/api/v1/ping) emit 200 "" ;;
\t*/api/v1/version) emit 200 "${SHIM_VERSION_FILE:-}" ;;
\t*/api/v1/harnesses) emit 200 "${SHIM_HARNESS_FILE:-}" ;;
esac
emit 404 ""
"""


def _record(ok: bool = True, failures: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "at": "2026-11-11T10:00:00Z",
        "trigger": "install",
        "ok": ok,
        "failures": failures or [],
        "skills": 7,
    }


def _harnesses(setup: dict[str, object] | None) -> dict[str, object]:
    row = {
        "name": "claude",
        "enabled": True,
        "last_readiness_at": None,
        "failing_check": None,
        "version_pin": "2.1.319",
        "lines": [{"check": "cli", "ok": True, "text": "ok"}],
        "models": [],
        "setup": setup,
    }
    return {"items": [row], "next_cursor": None}


def _version(bmad_installed: str | None = BMAD_PIN) -> dict[str, object]:
    return {
        "app_version": TAG,
        "kit_version": TAG,
        "bmad_version": BMAD_PIN,
        "bmad_installed": bmad_installed,
        "harness_versions": {"claude": "2.1.319"},
    }


def _run(
    *args: str, cwd: Path, env: dict[str, str] | None = None, answers: str | None = None
) -> subprocess.CompletedProcess[str]:
    dropped = {"GHCR_TOKEN", "GITHUB_TOKEN", "IMAGE_TAG", "DOCKER_CONFIG", *SIX}
    clean = {k: v for k, v in os.environ.items() if k not in dropped}
    return subprocess.run(  # fixed argv, no shell
        ["bash", str(cwd / "install.sh"), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**clean, **(env or {})},
        check=False,
        input=answers,
    )


@pytest.fixture
def folder(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    for name in (
        "install.sh",
        ".env.example",
        "docker-compose.yml",
        "release.env",
        "compose.override.yml",
    ):
        shutil.copy(DEPLOY_DIR / name, tmp_path / name)
    (tmp_path / "VERSION").write_text(f"{TAG}\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", DOCKER_SHIM), ("curl", CURL_SHIM)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    served = tmp_path / "served"
    served.mkdir()
    (served / "version.json").write_text(json.dumps(_version()))
    (served / "harnesses.json").write_text(json.dumps(_harnesses(_record())))
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "SHIM_DOCKER_LOG": str(tmp_path / "docker.log"),
        "SHIM_CURL_LOG": str(tmp_path / "curl.log"),
        "SHIM_CURL_ARGV": str(tmp_path / "curl.argv"),
        "SHIM_RUNNING": "postgres backend-api web-client",
        "SHIM_VERSION_FILE": str(served / "version.json"),
        "SHIM_HARNESS_FILE": str(served / "harnesses.json"),
        "GHCR_TOKEN": "ghp_folder_test_0123456789",
    }
    return tmp_path, env


def _log(path: Path, name: str) -> str:
    log = path / name
    return log.read_text() if log.is_file() else ""


def _hashes(path: Path) -> dict[str, str]:
    return {
        str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(path.rglob("*"))
        if p.is_file() and "bin" not in p.relative_to(path).parts[:1]
        and p.name not in {"docker.log", "curl.log", "curl.argv"}
        and "served" not in p.relative_to(path).parts[:1]
    }


def _install(folder: tuple[Path, dict[str, str]], *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    path, base = folder
    return _run("install", "--yes", "--no-pull", *args, cwd=path, env={**base, **env})


# ── AC1, AC2: the six values ─────────────────────────────────────────────────


@needs_bash
def test_install_writes_the_given_gateway_and_tracing_values(
    folder: tuple[Path, dict[str, str]],
) -> None:
    path, _ = folder

    result = _install(
        folder, LITELLM_BASE_URL="http://gw.example:4000", LANGFUSE_BASE_URL="http://lf.example"
    )

    assert result.returncode == 0, result.stdout + result.stderr
    text = (path / ".env").read_text()
    rendered = parse_env_example(path / ".env")
    assert rendered["LITELLM_BASE_URL"] == "http://gw.example:4000"
    assert rendered["LANGFUSE_BASE_URL"] == "http://lf.example"
    for name in ("LITELLM_API_KEY", "LITELLM_SPEND_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        assert f"\n{name}=\n" in text
    assert "IMAGE_TAG" not in text
    assert not (path / "llm-platform").exists()
    assert "llm-platform" not in _log(path, "docker.log") + _log(path, "curl.log")


@needs_bash
def test_install_with_nothing_given_leaves_all_six_blank(
    folder: tuple[Path, dict[str, str]],
) -> None:
    path, _ = folder

    result = _install(folder)

    assert result.returncode == 0, result.stdout + result.stderr
    text = (path / ".env").read_text()
    for name in SIX:
        assert f"\n{name}=\n" in text


@needs_bash
def test_install_asks_for_each_value_once_and_never_prints_a_key(
    folder: tuple[Path, dict[str, str]],
) -> None:
    path, base = folder
    answers = f"http://gw.example\n{SECRET}\n\n\npk-lf-public-0123456789\n{SECRET}-s\n"

    result = _run("install", "--no-pull", cwd=path, env=base, answers=answers)

    assert result.returncode == 0, result.stdout + result.stderr
    rendered = parse_env_example(path / ".env")
    assert rendered["LITELLM_BASE_URL"] == "http://gw.example"
    assert rendered["LITELLM_API_KEY"] == SECRET
    assert rendered["LITELLM_SPEND_KEY"] == ""
    assert rendered["LANGFUSE_BASE_URL"] == ""
    assert rendered["LANGFUSE_PUBLIC_KEY"] == "pk-lf-public-0123456789"
    assert rendered["LANGFUSE_SECRET_KEY"] == f"{SECRET}-s"
    for value in (SECRET, "pk-lf-public-0123456789"):
        assert value not in result.stdout + result.stderr


# ── AC3, AC4: an existing folder ─────────────────────────────────────────────


def _manifest(seeds: tuple[str, ...]) -> str:
    files = [{"path": s, "sha256": "0" * 64, "role": "seed"} for s in seeds]
    return json.dumps({"release": TAG, "files": files}, indent=2)


@needs_bash
@pytest.mark.parametrize("flags", [(), ("--no-bmad",)])
def test_install_changes_no_byte_of_a_present_file(
    folder: tuple[Path, dict[str, str]], flags: tuple[str, ...]
) -> None:
    path, _ = folder
    (path / ".env").write_text((DEPLOY_DIR / ".env.example").read_text().replace(
        "ORCHESTRATOR_TOKEN=change-me-long-random", "ORCHESTRATOR_TOKEN=keep-this-token"))
    (path / "templates").mkdir()
    (path / "templates" / "x.yaml").write_text("mine: true\n")
    (path / "compose.override.yml").write_text("services: {a: {}}\n")
    (path / "setup").mkdir()
    (path / "setup" / "bmad.choice").write_text("installed\n")
    (path / "product-files.json").write_text(_manifest(("compose.override.yml", "setup/bmad.choice")))
    before = _hashes(path)

    result = _install(folder, *flags, LITELLM_BASE_URL="http://gw.example")

    assert result.returncode == 0, result.stdout + result.stderr
    after = _hashes(path)
    for name, digest in before.items():
        assert after[name] == digest, name


@needs_bash
def test_install_creates_only_the_absent_seeds(folder: tuple[Path, dict[str, str]]) -> None:
    path, _ = folder
    (path / "compose.override.yml").unlink()
    (path / "product-files.json").write_text(_manifest(("compose.override.yml", "setup/bmad.choice")))
    before = set(_hashes(path))

    result = _install(folder)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (path / "compose.override.yml").read_bytes() == (
        DEPLOY_DIR / "compose.override.yml"
    ).read_bytes()
    assert (path / "setup" / "bmad.choice").read_text().strip() == "installed"
    new = {
        n for n in set(_hashes(path)) - before
        if n != ".env" and n.split("/")[0] not in {"logs", "backups", "diagnostics"}
    }
    assert new == {"compose.override.yml", "setup/bmad.choice"}


@needs_bash
def test_no_bmad_writes_removed_only_when_the_choice_is_absent(
    folder: tuple[Path, dict[str, str]],
) -> None:
    path, _ = folder

    assert _install(folder, "--no-bmad").returncode == 0
    assert (path / "setup" / "bmad.choice").read_text().strip() == "removed"

    (path / "setup" / "bmad.choice").write_text("installed\n")
    assert _install(folder, "--no-bmad").returncode == 0
    assert (path / "setup" / "bmad.choice").read_text() == "installed\n"


# ── AC5, AC6: setup under the hold ───────────────────────────────────────────


@needs_bash
def test_setup_runs_between_the_hold_and_its_release(folder: tuple[Path, dict[str, str]]) -> None:
    path, _ = folder

    result = _install(folder)

    assert result.returncode == 0, result.stdout + result.stderr
    calls = [line for line in _log(path, "curl.log").splitlines() if "/api/v1/" in line]
    kinds = [
        c.split()[0] + " " + c.split()[1].split("/api/v1/")[1]
        for c in calls
        if "instance/hold" in c or c.endswith("/harnesses") or "harnesses" in c
    ]
    assert kinds[:2] == ["POST instance/hold", "DELETE instance/hold"], kinds
    assert kinds[-1] == "GET harnesses"
    post = next(c for c in calls if c.startswith("POST"))
    assert json.loads(post.split(" ", 2)[2]) == {"ttl_seconds": 900, "reason": "install setup"}
    runs = [c for c in _log(path, "docker.log").splitlines() if " run --rm " in c]
    assert len(runs) == 1
    assert "--profile setup" in runs[0]
    assert f"-e ORCH_SETUP_TRIGGER=install -e ORCH_RELEASE={TAG}" in runs[0]
    assert runs[0].endswith(" setup")
    assert "claude" in result.stdout and "install" in result.stdout and "7" in result.stdout


@needs_bash
def test_the_hold_is_released_when_the_setup_run_fails(
    folder: tuple[Path, dict[str, str]],
) -> None:
    path, _ = folder
    failed = _record(False, [{"script": "10-x.sh", "reason": "exit 2"}])
    (path / "served" / "harnesses.json").write_text(json.dumps(_harnesses(failed)))

    result = _install(folder, SHIM_SETUP_RC="2")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "10-x.sh" in result.stdout + result.stderr
    calls = _log(path, "curl.log").splitlines()
    assert any(c.startswith("DELETE") and "instance/hold" in c for c in calls)


@needs_bash
def test_a_refused_hold_means_no_setup_run(folder: tuple[Path, dict[str, str]]) -> None:
    path, _ = folder

    result = _install(folder, SHIM_HOLD_CODE="409")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "409" in result.stdout + result.stderr
    assert " run --rm " not in _log(path, "docker.log")


# ── AC7: no platform surface ─────────────────────────────────────────────────


@needs_bash
def test_help_lists_no_platform_option_and_names_no_bmad(
    folder: tuple[Path, dict[str, str]],
) -> None:
    path, env = folder

    result = _run("--help", cwd=path, env=env)

    assert result.returncode == 0
    for word in ("--with-platform", "--no-platform", "llm-platform"):
        assert word not in result.stdout
    assert "--no-bmad" in result.stdout


@needs_bash
@pytest.mark.parametrize("args", [("start", "--no-platform"), ("install", "--with-platform")])
def test_the_platform_flags_are_unknown(
    folder: tuple[Path, dict[str, str]], args: tuple[str, ...]
) -> None:
    path, env = folder

    result = _run(*args, cwd=path, env=env)

    assert result.returncode != 0
    assert "unknown argument" in result.stderr


# ── AC8: doctor ──────────────────────────────────────────────────────────────


def _doctor(folder: tuple[Path, dict[str, str]], **env: str) -> subprocess.CompletedProcess[str]:
    path, base = folder
    assert _install(folder).returncode == 0
    return _run("doctor", cwd=path, env={**base, **env})


def _line(result: subprocess.CompletedProcess[str], name: str) -> list[str]:
    return [ln for ln in result.stdout.splitlines() if ln[6:].startswith(f"{name} ")]


@needs_bash
def test_doctor_setup_line_is_ok_with_a_good_record(folder: tuple[Path, dict[str, str]]) -> None:
    result = _doctor(folder)

    assert [ln.split()[0] for ln in _line(result, "setup")] == ["ok"]
    assert "platform" not in result.stdout


@needs_bash
def test_doctor_setup_line_fails_naming_each_failed_script(
    folder: tuple[Path, dict[str, str]],
) -> None:
    path, _ = folder
    failed = _record(False, [{"script": "10-x.sh", "reason": "r"}, {"script": "20-y.sh", "reason": "r"}])
    (path / "served" / "harnesses.json").write_text(json.dumps(_harnesses(failed)))

    result = _doctor(folder)

    assert result.returncode != 0
    text = " ".join(_line(result, "setup"))
    assert text.startswith("fail") and "10-x.sh" in text and "20-y.sh" in text


@needs_bash
def test_doctor_setup_line_fails_on_a_null_record(folder: tuple[Path, dict[str, str]]) -> None:
    path, _ = folder
    (path / "served" / "harnesses.json").write_text(json.dumps(_harnesses(None)))

    result = _doctor(folder)

    assert result.returncode != 0
    assert _line(result, "setup")[0].startswith("fail")


@needs_bash
def test_doctor_bmad_line_in_each_state(folder: tuple[Path, dict[str, str]]) -> None:
    path, _ = folder
    assert _line(_doctor(folder), "bmad")[0].startswith("ok")

    (path / "served" / "version.json").write_text(json.dumps(_version("6.0.0")))
    result = _run("doctor", cwd=path, env=folder[1])
    line = _line(result, "bmad")[0]
    assert line.startswith("fail") and "6.0.0" in line and BMAD_PIN in line

    (path / "setup" / "bmad.choice").write_text("removed\n")
    result = _run("doctor", cwd=path, env=folder[1])
    assert "removed by choice" in _line(result, "bmad")[0]
    assert _line(result, "bmad")[0].startswith("ok")


@needs_bash
def test_doctor_docker_engine_below_26_fails(folder: tuple[Path, dict[str, str]]) -> None:
    result = _doctor(folder, SHIM_ENGINE="25.0.3")

    assert result.returncode != 0
    line = " ".join(_line(result, "docker engine"))
    assert line.startswith("fail") and "26" in line and "volume subpaths" in line


@needs_bash
def test_doctor_docker_engine_26_or_later_is_ok(folder: tuple[Path, dict[str, str]]) -> None:
    assert _line(_doctor(folder), "docker engine")[0].startswith("ok")


@needs_bash
def test_doctor_release_pins_warn_naming_both_values(folder: tuple[Path, dict[str, str]]) -> None:
    path, base = folder
    assert _line(_doctor(folder), "release pins")[0].startswith("ok")

    with (path / ".env").open("a") as fh:
        fh.write("CODEX_VERSION=0.1.0\n")
    result = _run("doctor", cwd=path, env=base)

    assert result.returncode == 0
    line = " ".join(_line(result, "release pins"))
    assert line.startswith("warn") and "CODEX_VERSION" in line and "0.1.0" in line and "0.167.0" in line


@needs_bash
def test_doctor_warns_only_when_env_still_sets_image_tag(
    folder: tuple[Path, dict[str, str]],
) -> None:
    path, base = folder
    assert _line(_doctor(folder), "IMAGE_TAG") == []

    with (path / ".env").open("a") as fh:
        fh.write("IMAGE_TAG=1.0.0\n")
    result = _run("doctor", cwd=path, env=base)

    assert _line(result, "IMAGE_TAG")[0].startswith("warn")
    assert result.returncode == 0


@needs_bash
def test_doctor_without_release_env_warns_and_never_fails_on_it(
    folder: tuple[Path, dict[str, str]],
) -> None:
    path, base = folder
    assert _install(folder).returncode == 0
    (path / "release.env").unlink()

    result = _run("doctor", cwd=path, env=base)

    assert "release.env missing beside this script" in result.stdout
    assert _line(result, "bmad")[0].startswith("warn")
    assert _line(result, "release pins")[0].startswith("warn")
