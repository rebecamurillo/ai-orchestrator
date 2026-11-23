"""`MAX_INTERACTIVE_RUNS` (epic 3 story 2, AC7)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.infrastructure.dbos.config import engine_config
from orchestrator.infrastructure.settings import Settings

DEFAULT = 4
OVERRIDE = 7


def settings(env: dict[str, str], **extra: str) -> Settings:
    merged = {key: value for key, value in env.items() if key != "MAX_INTERACTIVE_RUNS"}
    merged.update(extra)
    return Settings(**{key.lower(): value for key, value in merged.items()})  # type: ignore[arg-type]


def test_the_default_is_four(env: dict[str, str]) -> None:
    assert settings(env).max_interactive_runs == DEFAULT


def test_the_environment_overrides_it(env: dict[str, str]) -> None:
    assert settings(env, MAX_INTERACTIVE_RUNS="7").max_interactive_runs == OVERRIDE


def test_zero_is_refused(env: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        settings(env, MAX_INTERACTIVE_RUNS="0")


def test_engine_config_carries_it(env: dict[str, str]) -> None:
    assert engine_config(settings(env)).max_interactive_runs == DEFAULT
