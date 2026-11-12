"""`install.sh setup`, `setup --reset`, `bmad remove`, `bmad install` — epic 3 story 4 (2026-11-11).

Each command makes one `--profile setup run --rm … setup` call between a hold `POST` and
`DELETE` when backend-api runs, and never restarts anything. Docker and curl are shims on PATH.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

DEPLOY_DIR = REPO_ROOT / "deploy"
TAG = "1.0.0-test"

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")

DOCKER_SHIM = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SHIM_DOCKER_LOG"
case "$*" in
\t"compose version") echo v2.99.0; exit 0 ;;
\t"compose version --short") echo 2.99.0; exit 0 ;;
\tinfo) exit 0 ;;
esac
case "$*" in
\t*" run --rm "*" setup"|*" run --rm "*" setup --reset") exit "${SHIM_SETUP_RC:-0}" ;;
\t*"ps --status running --services"*) printf '%s\\n' ${SHIM_RUNNING:-}; exit 0 ;;
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
emit() {
\tif [ -n "$out" ] && [ "$out" != "/dev/null" ] && [ -n "$2" ]; then cp "$2" "$out"; fi
\tprintf '%s' "$1"
\texit 0
}
case "$url" in
\t*/api/v1/instance/hold)
\t\tif [ "$method" = POST ]; then emit "${SHIM_HOLD_CODE:-200}" "${SHIM_HOLD_FILE:-}"; fi
\t\temit 200 "" ;;
\t*/api/v1/instance/activity) emit "${SHIM_ACTIVITY_CODE:-200}" "${SHIM_ACTIVITY_FILE:-}" ;;
\t*/healthz) emit "${SHIM_HEALTH_CODE:-200}" "" ;;
\t*/api/v1/harnesses) emit 200 "${SHIM_HARNESS_FILE:-}" ;;
esac
emit 404 ""
"""

IDLE = {"working": [], "in_engine": [], "hold": None, "dbos_application_version": "x"}
STEP = {
    "run_id": "R1",
    "run_label": "L1",
    "path": "build/P",
    "kind": "agent",
    "started_at": "2026-11-11T10:05:00Z",
}


def _harnesses(ok: bool = True, failures: list[str] | None = None) -> dict[str, object]:
    setup = {
        "at": "2026-11-11T10:00:00Z",
        "trigger": "on-demand",
        "ok": ok,
        "failures": failures or [],
        "skills": 7,
    }
    return {
        "items": [{"name": "claude", "enabled": True, "setup": setup}],
        "next_cursor": None,
    }


Folder = tuple[Path, dict[str, str]]


@pytest.fixture
def folder(tmp_path: Path) -> Folder:
    for name in (
        "install.sh",
        ".env.example",
        "docker-compose.yml",
        "release.env",
        "compose.override.yml",
    ):
        shutil.copy(DEPLOY_DIR / name, tmp_path / name)
    (tmp_path / "VERSION").write_text(f"{TAG}\n")
    (tmp_path / "setup").mkdir()
    (tmp_path / "setup" / "bmad.choice").write_text("installed\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", DOCKER_SHIM), ("curl", CURL_SHIM)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    served = tmp_path / "served"
    served.mkdir()
    (served / "harnesses.json").write_text(json.dumps(_harnesses()))
    (served / "activity.json").write_text(json.dumps(IDLE))
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "SHIM_DOCKER_LOG": str(tmp_path / "docker.log"),
        "SHIM_CURL_LOG": str(tmp_path / "curl.log"),
        "SHIM_RUNNING": "postgres backend-api web-client",
        "SHIM_HARNESS_FILE": str(served / "harnesses.json"),
        "SHIM_ACTIVITY_FILE": str(served / "activity.json"),
    }
    made = subprocess.run(  # fixed argv, no shell
        ["bash", str(tmp_path / "install.sh"), "env", "--yes", "--tag", TAG],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, **env},
        check=False,
    )
    assert made.returncode == 0, made.stderr
    return tmp_path, env


def _run(folder: Folder, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    path, base = folder
    return subprocess.run(  # fixed argv, no shell
        ["bash", str(path / "install.sh"), *args],
        capture_output=True,
        text=True,
        cwd=path,
        env={**os.environ, **base, **env},
        check=False,
    )


def _log(path: Path, name: str) -> list[str]:
    log = path / name
    return log.read_text().splitlines() if log.is_file() else []


def _runs(path: Path) -> list[str]:
    return [ln for ln in _log(path, "docker.log") if " run --rm " in ln]


def _hold_calls(path: Path) -> list[str]:
    return [ln for ln in _log(path, "curl.log") if "/instance/hold" in ln]


def _hashes(path: Path) -> dict[str, str]:
    skip = {"bin", "served"}
    return {
        str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(path.rglob("*"))
        if p.is_file()
        and p.relative_to(path).parts[0] not in skip
        and p.name not in {"docker.log", "curl.log"}
    }


def _serve(path: Path, name: str, body: object) -> str:
    target = path / "served" / name
    target.write_text(json.dumps(body))
    return str(target)


def _choice(path: Path) -> str:
    return (path / "setup" / "bmad.choice").read_text()


# ── AC1, AC2 ─────────────────────────────────────────────────────────────────


@needs_bash
def test_bmad_remove_writes_the_choice_and_runs_setup_under_the_hold(folder: Folder) -> None:
    path, _ = folder

    result = _run(folder, "bmad", "remove")

    assert result.returncode == 0, result.stderr + result.stdout
    assert _choice(path) == "removed\n"
    runs = _runs(path)
    assert len(runs) == 1
    assert f"--profile setup run --rm -e ORCH_SETUP_TRIGGER=on-demand -e ORCH_RELEASE={TAG}" in runs[0]
    assert runs[0].endswith(" setup")
    curls = _log(path, "curl.log")
    post = next(i for i, ln in enumerate(curls) if ln.startswith("POST") and "/instance/hold" in ln)
    delete = next(i for i, ln in enumerate(curls) if ln.startswith("DELETE") and "/instance/hold" in ln)
    assert '{"ttl_seconds": 900, "reason": "setup"}' in curls[post]
    assert post < delete
    assert "/api/v1/harnesses" in curls[delete + 1]


@needs_bash
def test_bmad_install_writes_installed_over_removed_and_over_absent(folder: Folder) -> None:
    path, _ = folder
    (path / "setup" / "bmad.choice").write_text("removed\n")

    first = _run(folder, "bmad", "install")

    assert first.returncode == 0, first.stderr
    assert _choice(path) == "installed\n"
    assert len(_runs(path)) == 1
    assert len(_hold_calls(path)) == 2

    (path / "setup" / "bmad.choice").unlink()
    second = _run(folder, "bmad", "install")

    assert second.returncode == 0, second.stderr
    assert _choice(path) == "installed\n"


# ── AC3 ──────────────────────────────────────────────────────────────────────


@needs_bash
def test_setup_reset_passes_the_trigger_and_the_flag_and_plain_setup_does_not(
    folder: Folder,
) -> None:
    path, _ = folder

    reset = _run(folder, "setup", "--reset")
    plain = _run(folder, "setup")

    assert reset.returncode == 0, reset.stderr
    assert plain.returncode == 0, plain.stderr
    first, second = _runs(path)
    assert "-e ORCH_SETUP_TRIGGER=reset" in first
    assert first.endswith(" setup --reset")
    assert "-e ORCH_SETUP_TRIGGER=on-demand" in second
    assert second.endswith(" setup")
    assert _choice(path) == "installed\n"


# ── AC4, AC5 ─────────────────────────────────────────────────────────────────


@needs_bash
@pytest.mark.parametrize("args", [("setup",), ("bmad", "remove")])
def test_a_working_step_refuses_with_exit_3_and_changes_nothing(
    folder: Folder, args: tuple[str, ...]
) -> None:
    path, _ = folder
    activity = _serve(path, "busy.json", {**IDLE, "working": [STEP]})
    before = _hashes(path)

    result = _run(folder, *args, SHIM_ACTIVITY_FILE=activity)

    assert result.returncode == 3
    assert "refused: nothing was changed" in result.stderr
    assert "run R1 (L1) step build/P (agent) working since 2026-11-11T10:05:00Z" in result.stderr
    assert _runs(path) == []
    assert _hold_calls(path) == []
    assert _hashes(path) == before


@needs_bash
def test_a_409_hold_refuses_naming_the_step_and_other_codes_exit_1(folder: Folder) -> None:
    path, _ = folder
    body = _serve(path, "hold.json", {"errors": [STEP]})
    before = _hashes(path)

    busy = _run(folder, "bmad", "remove", SHIM_HOLD_CODE="409", SHIM_HOLD_FILE=body)

    assert busy.returncode == 3
    assert "run R1 (L1) step build/P (agent)" in busy.stderr
    assert _runs(path) == []
    assert not any(ln.startswith("DELETE") for ln in _log(path, "curl.log"))
    assert _hashes(path) == before

    other = _run(folder, "setup", SHIM_HOLD_CODE="500")

    assert other.returncode == 1
    assert "500" in other.stderr
    assert _runs(path) == []


# ── AC6 ──────────────────────────────────────────────────────────────────────


@needs_bash
@pytest.mark.parametrize("down", ["SHIM_HEALTH_CODE", "SHIM_ACTIVITY_CODE"])
def test_an_api_that_does_not_answer_refuses_with_exit_1(folder: Folder, down: str) -> None:
    path, _ = folder

    result = _run(folder, "setup", **{down: "000"})

    assert result.returncode == 1
    assert "refused: nothing was changed" in result.stderr
    assert "did not answer" in result.stderr
    assert _runs(path) == []


@needs_bash
@pytest.mark.parametrize(("rc", "expected"), [("0", 0), ("2", 2)])
def test_without_backend_api_no_hold_is_taken_and_the_exit_is_the_runners(
    folder: Folder, rc: str, expected: int
) -> None:
    path, _ = folder

    result = _run(folder, "setup", SHIM_RUNNING="postgres", SHIM_SETUP_RC=rc)

    assert result.returncode == expected
    assert len(_runs(path)) == 1
    assert _log(path, "curl.log") == []
    assert "record not read" in result.stdout


# ── AC7 ──────────────────────────────────────────────────────────────────────


@needs_bash
@pytest.mark.parametrize("rc", ["2", "0"])
def test_a_failed_run_still_releases_the_hold_and_exits_2(folder: Folder, rc: str) -> None:
    path, _ = folder
    served = _serve(path, "bad.json", _harnesses(ok=False, failures=["10-x.sh"]))

    result = _run(folder, "setup", SHIM_SETUP_RC=rc, SHIM_HARNESS_FILE=served)

    assert result.returncode == 2
    assert any(ln.startswith("DELETE") for ln in _log(path, "curl.log"))
    assert "10-x.sh" in result.stdout


# ── AC8 ──────────────────────────────────────────────────────────────────────


@needs_bash
@pytest.mark.parametrize(
    "args", [("setup",), ("setup", "--reset"), ("bmad", "remove"), ("bmad", "install")]
)
def test_no_command_restarts_or_removes_a_service(folder: Folder, args: tuple[str, ...]) -> None:
    path, _ = folder

    result = _run(folder, *args)

    assert result.returncode == 0, result.stderr
    for line in _log(path, "docker.log"):
        padded = f" {line} "
        scrubbed = padded.replace(" run --rm ", " ")
        for word in (" up ", "restart", " stop", " down ", " rm ", "llm-platform"):
            assert word not in scrubbed, line


# ── AC9 ──────────────────────────────────────────────────────────────────────


@needs_bash
def test_help_lists_the_four_commands_and_keeps_no_bmad(folder: Folder) -> None:
    result = _run(folder, "--help")

    assert result.returncode == 0
    for text in ("setup [--reset]", "bmad remove", "bmad install", "--no-bmad"):
        assert text in result.stdout
    assert "platform" not in result.stdout.lower()


@needs_bash
@pytest.mark.parametrize(
    ("args", "usage"),
    [
        (("install", "--reset"), "./install.sh setup --reset"),
        (("bmad",), "bmad remove"),
        (("bmad", "frobnicate"), "bmad remove"),
        (("bmad", "remove", "install"), "bmad remove"),
        (("bmad", "install", "setup"), "bmad install"),
    ],
)
def test_bad_usage_names_the_right_form_and_calls_nothing(
    folder: Folder, args: tuple[str, ...], usage: str
) -> None:
    path, _ = folder
    before = _hashes(path)

    result = _run(folder, *args)

    assert result.returncode != 0
    assert usage in result.stderr
    assert _log(path, "docker.log") == []
    assert _hashes(path) == before
