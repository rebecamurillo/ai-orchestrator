"""`deploy/.env.example` is the consumer's copy of the contract; `make lint` fails when it
drifts from the root `.env.example` (hard rule 8, extended to the copy a consumer fills in).

`test_env_contract.py` holds the root contract against `Settings`; this module holds the
deploy copy against the root contract, through the same script the gate runs. The success
path is deliberately silent — `test_env_contract.py` pins the script's stdout to exactly
one line, so agreement here must add nothing to it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from check_env_contract import (
    DEPLOY_ONLY_VARIABLES,
    compare_deploy,
    env_example_variables,
    settings_variables,
)

from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT, parse_env_example

SCRIPT = REPO_ROOT / "scripts" / "check_env_contract.py"
DEPLOY_ENV_EXAMPLE = REPO_ROOT / "deploy" / ".env.example"


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the check the way `make lint` does — as a command, in this interpreter."""
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "backend-api" / "src")}
    return subprocess.run(  # fixed argv, no shell
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        check=False,
    )


# ── the committed state ──────────────────────────────────────────────────────


def test_the_committed_deploy_copy_matches_the_contract() -> None:
    lost, stray, gone = compare_deploy(
        env_example_variables(), env_example_variables(DEPLOY_ENV_EXAMPLE)
    )

    assert lost == []
    assert stray == []
    assert gone == []


def test_the_check_still_passes_as_a_command_with_the_deploy_copy_in_scope() -> None:
    result = _run_script()

    assert result.returncode == 0, result.stdout + result.stderr


def test_agreement_adds_nothing_to_stdout() -> None:
    """One line — the root success line `test_env_contract.py` pins — and no second."""
    result = _run_script()

    assert len(result.stdout.strip().splitlines()) == 1


# ── the deploy-only set ──────────────────────────────────────────────────────


def test_the_deploy_only_set_is_exactly_the_compose_cli_variables() -> None:
    assert DEPLOY_ONLY_VARIABLES == {"IMAGE_TAG", "COMPOSE_PROJECT_NAME", "BIND_ADDRESS"}
    assert DEPLOY_ONLY_VARIABLES <= env_example_variables(DEPLOY_ENV_EXAMPLE)


def test_no_deploy_only_variable_is_a_settings_field_or_a_root_contract_line() -> None:
    """They are docker-CLI configuration; a root line for one would fail the root check,
    and a Settings field for one would make it application configuration (AD-20)."""
    assert not (DEPLOY_ONLY_VARIABLES & settings_variables())
    assert not (DEPLOY_ONLY_VARIABLES & env_example_variables())


# ── drift, in every direction ────────────────────────────────────────────────


def test_a_contract_variable_lost_from_the_deploy_copy_is_named() -> None:
    lost, stray, _gone = compare_deploy({"LOG_LEVEL", "GITHUB_TOKEN"}, {"LOG_LEVEL"})

    assert lost == ["GITHUB_TOKEN"]
    assert stray == []


def test_a_stray_deploy_variable_is_named() -> None:
    _lost, stray, _gone = compare_deploy({"LOG_LEVEL"}, {"LOG_LEVEL", "STRAY_VARIABLE"})

    assert stray == ["STRAY_VARIABLE"]


def test_the_deploy_only_variables_are_not_stray() -> None:
    _lost, stray, gone = compare_deploy(set(), set(DEPLOY_ONLY_VARIABLES))

    assert stray == []
    assert gone == []


def test_deleting_a_deploy_only_variable_is_caught() -> None:
    """The consumer compose interpolates all three; losing one fails the stack at `up`."""
    _lost, _stray, gone = compare_deploy(set(), set(DEPLOY_ONLY_VARIABLES) - {"IMAGE_TAG"})

    assert gone == ["IMAGE_TAG"]


def test_the_script_reports_a_lost_variable_and_exits_non_zero(tmp_path: Path) -> None:
    trimmed = tmp_path / ".env.example"
    kept = [
        line
        for line in DEPLOY_ENV_EXAMPLE.read_text().splitlines(keepends=True)
        if not line.startswith("GITHUB_TOKEN=")
    ]
    trimmed.write_text("".join(kept))

    result = _run_script("--deploy-env-example", str(trimmed))

    assert result.returncode != 0
    assert "GITHUB_TOKEN" in result.stderr


def test_the_script_reports_a_missing_deploy_file_and_exits_non_zero(tmp_path: Path) -> None:
    result = _run_script("--deploy-env-example", str(tmp_path / "absent.env"))

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "absent.env" in result.stdout + result.stderr


def test_the_deploy_check_runs_only_after_the_root_check_passes(tmp_path: Path) -> None:
    """A root failure returns before the deploy comparison, so its report names the root
    file's drift and never a cascade of deploy lines caused by the same edit."""
    trimmed = tmp_path / ".env.example"
    kept = [
        line
        for line in ENV_EXAMPLE.read_text().splitlines(keepends=True)
        if not line.startswith("LOG_LEVEL=")
    ]
    trimmed.write_text("".join(kept))

    result = _run_script("--env-example", str(trimmed))

    assert result.returncode != 0
    assert "deploy contract:" not in result.stderr


# ── the harness CLI pins agree ───────────────────────────────────────────────
#
# spec-harness-upgrade-survives-redeploy (2026-10-29): `install.sh upgrade` reads the pins from
# the new image's `deploy/.env.example` and a dev build from the root one; a value that
# differs between the two would install one CLI in development and another on a client.


@pytest.mark.parametrize("variable", ["CLAUDE_CODE_VERSION", "CODEX_VERSION", "OPENCODE_VERSION"])
def test_each_harness_pin_has_the_same_value_in_both_copies(variable: str) -> None:
    root = parse_env_example(ENV_EXAMPLE)
    deploy = parse_env_example(DEPLOY_ENV_EXAMPLE)

    assert root[variable]
    assert deploy[variable] == root[variable]
