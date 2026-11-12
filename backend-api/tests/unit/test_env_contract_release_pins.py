"""`deploy/release.env` and the commented pins of `deploy/.env.example` (story 5, epic 2).

The release's version pins live in `deploy/release.env`; the consumer's `.env.example`
carries them only as commented declarations. `check_env_contract.py` counts a pin as
declared when it is both commented there and set in `release.env`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from check_env_contract import (
    RELEASE_PIN_VARIABLES,
    commented_declarations,
    compare_release,
)

from tests.unit.conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "check_env_contract.py"
DEPLOY_ENV_EXAMPLE = REPO_ROOT / "deploy" / ".env.example"
RELEASE_ENV = REPO_ROOT / "deploy" / "release.env"

PINS = sorted(RELEASE_PIN_VARIABLES)


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "backend-api" / "src")}
    return subprocess.run(  # fixed argv, no shell
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        check=False,
    )


def _release(tmp_path: Path, names: list[str]) -> Path:
    path = tmp_path / "release.env"
    path.write_text("".join(f"{name}=1\n" for name in names))
    return path


def _deploy_copy(tmp_path: Path, mutate) -> Path:  # type: ignore[no-untyped-def]
    path = tmp_path / ".env.example"
    path.write_text(mutate(DEPLOY_ENV_EXAMPLE.read_text()))
    return path


def test_the_six_pins_are_the_release_pin_set() -> None:
    assert RELEASE_PIN_VARIABLES == {
        "BMAD_VERSION",
        "DBOS_APPLICATION_VERSION",
        "CLAUDE_CODE_VERSION",
        "CODEX_VERSION",
        "OPENCODE_VERSION",
        "LANGFUSE_OPENCODE_PLUGIN_VERSION",
    }


# ── commented_declarations ───────────────────────────────────────────────────


def test_commented_declarations_matches_a_commented_assignment(tmp_path: Path) -> None:
    path = tmp_path / "x"
    path.write_text(
        "# CODEX_VERSION=  # set by release.env; uncomment to override\n"
        "#OPENCODE_VERSION=\n"
        "# NOTIFY_WEBHOOK_URL: a prose line\n"
        "#   npm view opencode-ai version   # OPENCODE_VERSION\n"
        "# lowercase=1\n"
        "REAL=1\n"
    )

    assert commented_declarations(path) == {"CODEX_VERSION", "OPENCODE_VERSION"}


# ── compare_release ──────────────────────────────────────────────────────────


def test_compare_release_agreement_is_four_empty_lists() -> None:
    pins = set(RELEASE_PIN_VARIABLES)

    assert compare_release(set(), pins, pins) == ([], [], [], [])


def test_compare_release_names_a_pin_missing_from_release_env() -> None:
    pins = set(RELEASE_PIN_VARIABLES)

    missing, stray, uncommented, undeclared = compare_release(set(), pins, pins - {"CODEX_VERSION"})

    assert (missing, stray, uncommented, undeclared) == (["CODEX_VERSION"], [], [], [])


def test_compare_release_names_a_stray_release_env_name() -> None:
    pins = set(RELEASE_PIN_VARIABLES)

    result = compare_release(set(), pins, pins | {"EXTRA_THING"})

    assert result == ([], ["EXTRA_THING"], [], [])


def test_compare_release_names_a_pin_set_uncommented_in_the_deploy_copy() -> None:
    pins = set(RELEASE_PIN_VARIABLES)

    result = compare_release({"CODEX_VERSION"}, pins - {"CODEX_VERSION"}, pins)

    assert result == ([], [], ["CODEX_VERSION"], ["CODEX_VERSION"])
    assert compare_release({"CODEX_VERSION"}, pins, pins) == ([], [], ["CODEX_VERSION"], [])


def test_compare_release_names_a_pin_not_commented_in_the_deploy_copy() -> None:
    pins = set(RELEASE_PIN_VARIABLES)

    result = compare_release(set(), pins - {"OPENCODE_VERSION"}, pins)

    assert result == ([], [], [], ["OPENCODE_VERSION"])


# ── the script as a command ──────────────────────────────────────────────────


def test_the_committed_files_agree_with_one_stdout_line() -> None:
    result = _run_script()

    assert result.returncode == 0, result.stdout + result.stderr
    assert len(result.stdout.strip().splitlines()) == 1


def test_a_pin_missing_from_release_env_fails_naming_it(tmp_path: Path) -> None:
    release = _release(tmp_path, [name for name in PINS if name != "CODEX_VERSION"])

    result = _run_script("--release-env", str(release))

    assert result.returncode != 0
    assert "CODEX_VERSION" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_stray_name_in_release_env_fails_naming_it(tmp_path: Path) -> None:
    release = _release(tmp_path, [*PINS, "STRAY_NAME"])

    result = _run_script("--release-env", str(release))

    assert result.returncode != 0
    assert "STRAY_NAME" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_pin_set_uncommented_in_the_deploy_copy_fails_naming_it(tmp_path: Path) -> None:
    deploy = _deploy_copy(
        tmp_path,
        lambda text: text.replace("# CODEX_VERSION=", "CODEX_VERSION=", 1),
    )

    result = _run_script("--deploy-env-example", str(deploy))

    assert result.returncode != 0
    assert "CODEX_VERSION" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_pin_neither_commented_nor_set_fails_naming_it(tmp_path: Path) -> None:
    deploy = _deploy_copy(
        tmp_path,
        lambda text: (
            "\n".join(
                line for line in text.splitlines() if not line.startswith("# OPENCODE_VERSION=")
            )
            + "\n"
        ),
    )

    result = _run_script("--deploy-env-example", str(deploy))

    assert result.returncode != 0
    assert "OPENCODE_VERSION" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_missing_release_env_fails_naming_the_file(tmp_path: Path) -> None:
    result = _run_script("--release-env", str(tmp_path / "release.env"))

    assert result.returncode != 0
    assert "release.env" in result.stderr
    assert "Traceback" not in result.stderr


def test_release_drift_does_not_hide_deploy_copy_drift(tmp_path: Path) -> None:
    release = _release(tmp_path, [name for name in PINS if name != "CODEX_VERSION"])
    deploy = _deploy_copy(
        tmp_path,
        lambda text: (
            "\n".join(line for line in text.splitlines() if not line.startswith("POSTGRES_DB="))
            + "\n"
        ),
    )

    result = _run_script("--release-env", str(release), "--deploy-env-example", str(deploy))

    assert result.returncode != 0
    assert "CODEX_VERSION" in result.stderr
    assert "POSTGRES_DB" in result.stderr
    assert "Traceback" not in result.stderr
