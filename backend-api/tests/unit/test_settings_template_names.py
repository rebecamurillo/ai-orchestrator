"""`INIT_TEMPLATE` and `READINESS_TEMPLATE`: the two Templates an instance dispatches by
name (AD-20, Operator decision 2026-09-30: no template name hardcoded in product code).

Both are *names*, never `name@version`: the latest stored version of the configured name is
resolved at dispatch (AD-7, AD-15), so an instance that stores a second version of either
gets it without a configuration change.
"""

from __future__ import annotations

import pytest

from orchestrator.infrastructure.settings import Settings


def test_the_two_template_names_default_to_the_shipped_exemplars(env: dict[str, str]) -> None:
    settings = Settings()  # type: ignore[call-arg]

    assert settings.init_template == "repo-init"
    assert settings.readiness_template == "epic"


def test_an_instance_may_point_both_at_its_own_templates(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INIT_TEMPLATE", "house-init")
    monkeypatch.setenv("READINESS_TEMPLATE", "house-epic")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.init_template == "house-init"
    assert settings.readiness_template == "house-epic"


@pytest.mark.parametrize("name", ["INIT_TEMPLATE", "READINESS_TEMPLATE"])
def test_a_blank_name_refuses_rather_than_dispatching_nothing(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "")

    with pytest.raises(ValueError):
        Settings()  # type: ignore[call-arg]


@pytest.mark.parametrize("name", ["INIT_TEMPLATE", "READINESS_TEMPLATE"])
def test_the_contract_declares_both(env_example: dict[str, str], name: str) -> None:
    assert name in env_example
