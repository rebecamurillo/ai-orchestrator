"""The deploy package mounts and documents the operator's template folder (story 4, AD-26).

New assertions live here, not in `test_deploy_compose.py` or `test_deploy_env_contract.py`."""

from __future__ import annotations

import subprocess
import sys

from tests.unit.conftest import REPO_ROOT, parse_env_example

DEPLOY = REPO_ROOT / "deploy"
MOUNT = "./templates:/app/operator-templates:ro"


def test_the_backend_mounts_the_folder_read_only() -> None:
    compose = (DEPLOY / "docker-compose.yml").read_text()

    assert compose.count(MOUNT) == 1
    backend = compose.split("  backend-api:")[1].split("\n  web-client:")[0]
    assert MOUNT in backend


def test_both_env_examples_carry_the_variable() -> None:
    assert parse_env_example(REPO_ROOT / ".env.example")["OPERATOR_TEMPLATES_DIR"] == ""
    deploy = parse_env_example(DEPLOY / ".env.example")["OPERATOR_TEMPLATES_DIR"]
    assert deploy == "/app/operator-templates"


def test_the_folder_is_documented_and_holds_no_workflow_file() -> None:
    folder = DEPLOY / "templates"

    assert (folder / "README.md").is_file()
    assert list(folder.glob("*.yaml")) == []
    assert "deploy/templates/*.yaml" in (REPO_ROOT / ".gitignore").read_text()


def test_the_env_contract_check_passes() -> None:
    done = subprocess.run(
        [sys.executable, "-I", str(REPO_ROOT / "scripts" / "check_env_contract.py")],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT / "backend-api",
    )

    assert done.returncode == 0, done.stdout + done.stderr
