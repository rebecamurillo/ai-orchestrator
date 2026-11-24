"""`RunDefaultsIn`: the body of `PUT /projects/{id}/run-defaults` (story 1 of epic 6)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from orchestrator.api.schemas.project_settings import InitiativeFolderIn, RunDefaultsIn

FULL: dict[str, Any] = {
    "default_budget_usd": "25.00",
    "default_harness": "claude",
    "default_model": "claude-opus-5-5",
    "default_autonomy": "auto",
    "default_senior_model": "claude-opus-5-5",
}


def refused(body: dict[str, Any]) -> ValidationError:
    with pytest.raises(ValidationError) as caught:
        RunDefaultsIn.model_validate(body)
    return caught.value


def test_a_full_body_maps_to_the_use_case_dataclass() -> None:
    defaults = RunDefaultsIn.model_validate(FULL).as_defaults()

    assert defaults.default_budget_usd == Decimal("25.00")
    assert defaults.default_harness == "claude"
    assert defaults.default_model == "claude-opus-5-5"
    assert defaults.default_autonomy == "auto"
    assert defaults.default_senior_model == "claude-opus-5-5"


def test_all_null_is_accepted() -> None:
    body = dict.fromkeys(FULL)
    assert RunDefaultsIn.model_validate(body).as_defaults().default_budget_usd is None


@pytest.mark.parametrize("key", list(FULL))
def test_a_missing_key_is_refused(key: str) -> None:
    body = {k: v for k, v in FULL.items() if k != key}
    assert refused(body).errors()[0]["loc"] == (key,)


def test_an_unknown_key_is_refused() -> None:
    assert refused({**FULL, "extra": 1}).errors()[0]["loc"] == ("extra",)


@pytest.mark.parametrize("budget", ["0", "-1", "1.1234567"])
def test_a_bad_budget_names_its_field(budget: str) -> None:
    assert refused({**FULL, "default_budget_usd": budget}).errors()[0]["loc"] == (
        "default_budget_usd",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("default_harness", "Claude"),
        ("default_harness", ""),
        ("default_model", ""),
        ("default_senior_model", ""),
        ("default_autonomy", "manual"),
    ],
)
def test_a_rule_breaking_value_is_refused(field: str, value: str) -> None:
    assert refused({**FULL, field: value}).errors()[0]["loc"] == (field,)


def test_initiative_folder_in_accepts_a_string_and_refuses_a_missing_or_unknown_key() -> None:
    # story 2 of epic 6, 2026-11-22
    assert (
        InitiativeFolderIn.model_validate({"initiative_folder": "specs"}).initiative_folder
        == "specs"
    )
    for body in ({}, {"initiative_folder": "a", "extra": 1}):
        with pytest.raises(ValidationError):
            InitiativeFolderIn.model_validate(body)
