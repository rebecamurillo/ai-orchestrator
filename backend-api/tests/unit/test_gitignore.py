"""The ignore rules are load-bearing: `.env.example` must stay committable, `.env` must not.

Both are order-dependent — git applies the last matching pattern — and nothing else in the
suite reads the repository through git, so without this the rules can invert silently.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from tests.unit.conftest import REPO_ROOT

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _is_ignored(path: str) -> bool:
    result = subprocess.run(  # fixed argv, no shell
        ["git", "check-ignore", "-q", "--no-index", path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        pytest.fail(f"git check-ignore failed: {result.stderr}")
    return result.returncode == 0


@pytest.mark.parametrize("path", [".env", ".env.local", ".env.production"])
def test_a_filled_env_file_is_ignored(path: str) -> None:
    assert _is_ignored(path)


def test_the_committed_contract_is_not_ignored() -> None:
    assert not _is_ignored(".env.example")


@pytest.mark.parametrize(
    "path",
    [
        "backend-api/.venv/pyvenv.cfg",
        "backend-api/.mypy_cache/x",
        "backend-api/.ruff_cache/x",
        "backend-api/.pytest_cache/x",
        "backend-api/.import_linter_cache/x",
        "backend-api/src/orchestrator/__pycache__/main.cpython-314.pyc",
        "web-client/node_modules/x",
    ],
)
def test_generated_trees_stay_out_of_the_repository(path: str) -> None:
    assert _is_ignored(path)


def test_the_bmad_rules_that_predate_this_story_still_apply() -> None:
    assert _is_ignored("_bmad/config.user.toml")
    assert _is_ignored(".claude/skills/bmad-build")
    assert _is_ignored(".DS_Store")


def test_guidelines_and_the_readme_are_tracked() -> None:
    assert not _is_ignored("GUIDELINES.md")
    assert not _is_ignored("README.md")
