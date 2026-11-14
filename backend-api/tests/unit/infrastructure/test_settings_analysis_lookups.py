"""`ANALYSIS_LOOKUPS` (epic 5 story 3, AC8)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT, parse_env_example
from tests.unit.test_settings_defaults import minimal_env  # noqa: F401 — the fixture

from orchestrator.infrastructure.settings import Settings

DEPLOY_ENV_EXAMPLE = REPO_ROOT / "deploy" / ".env.example"


@pytest.mark.usefixtures("minimal_env")
def test_lookups_are_on_when_the_variable_is_unset() -> None:
    assert Settings().analysis_lookups == "on"


@pytest.mark.usefixtures("minimal_env")
def test_off_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_LOOKUPS", "off")
    assert Settings().analysis_lookups == "off"


@pytest.mark.usefixtures("minimal_env")
def test_a_third_value_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_LOOKUPS", "maybe")
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("path", [ENV_EXAMPLE, DEPLOY_ENV_EXAMPLE])
def test_both_env_examples_declare_on(path: object) -> None:
    assert parse_env_example(path)["ANALYSIS_LOOKUPS"] == "on"  # type: ignore[arg-type]
