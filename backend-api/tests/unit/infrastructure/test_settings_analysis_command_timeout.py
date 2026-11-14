"""`ANALYSIS_COMMAND_TIMEOUT_MIN` (epic 6 story 1, AC9)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT, parse_env_example
from tests.unit.test_settings_defaults import minimal_env  # noqa: F401 — the fixture

from orchestrator.infrastructure.settings import Settings

DEFAULT = 20
OVERRIDE = 5
DEPLOY_ENV_EXAMPLE = REPO_ROOT / "deploy" / ".env.example"


@pytest.mark.usefixtures("minimal_env")
def test_the_timeout_is_twenty_minutes_when_unset() -> None:
    assert Settings().analysis_command_timeout_min == DEFAULT


@pytest.mark.usefixtures("minimal_env")
def test_an_override_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_COMMAND_TIMEOUT_MIN", str(OVERRIDE))
    assert Settings().analysis_command_timeout_min == OVERRIDE


@pytest.mark.usefixtures("minimal_env")
def test_zero_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_COMMAND_TIMEOUT_MIN", "0")
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("path", [ENV_EXAMPLE, DEPLOY_ENV_EXAMPLE])
def test_both_env_examples_declare_twenty(path: object) -> None:
    assert parse_env_example(path)["ANALYSIS_COMMAND_TIMEOUT_MIN"] == "20"  # type: ignore[arg-type]
