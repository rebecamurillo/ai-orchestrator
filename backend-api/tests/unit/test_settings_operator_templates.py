"""`OPERATOR_TEMPLATES_DIR` (story 4, AD-26): blank is off."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.infrastructure.settings import Settings


def test_a_blank_variable_is_unset(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPERATOR_TEMPLATES_DIR", "")

    assert Settings().operator_templates_dir is None  # type: ignore[call-arg]


def test_a_value_is_a_path(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPERATOR_TEMPLATES_DIR", "/app/operator-templates")

    assert Settings().operator_templates_dir == Path("/app/operator-templates")  # type: ignore[call-arg]
