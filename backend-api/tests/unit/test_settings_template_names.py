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


@pytest.mark.parametrize(
    ("name", "field", "default"),
    [
        ("INIT_TEMPLATE", "init_template", "repo-init"),
        ("READINESS_TEMPLATE", "readiness_template", "epic"),
    ],
)
def test_a_blank_name_in_the_environment_means_the_default(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, name: str, field: str, default: str
) -> None:
    """Revised at the merge of the two-tier contract (Operator decision 2026-09-20, reaffirmed
    2026-09-30: a blank environment value is the same as an absent one): `INIT_TEMPLATE=`
    no longer refuses start-up, it dispatches the shipped exemplar like an unset line does."""
    monkeypatch.setenv(name, "")

    assert getattr(Settings(), field) == default  # type: ignore[call-arg]


@pytest.mark.parametrize("field", ["init_template", "readiness_template"])
def test_an_explicit_blank_name_still_refuses(env: dict[str, str], field: str) -> None:
    """The blank-means-unset rule is the environment source's; a value handed to the model
    directly keeps `min_length=1`, so nothing can dispatch a Template with no name."""
    with pytest.raises(ValueError):
        Settings(**{field: ""})  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["INIT_TEMPLATE", "READINESS_TEMPLATE"])
def test_the_contract_declares_both(env_example: dict[str, str], name: str) -> None:
    assert name in env_example
