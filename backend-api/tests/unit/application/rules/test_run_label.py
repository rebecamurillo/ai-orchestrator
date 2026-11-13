"""The Run label rules (story 3; SPEC CAP-3; ARCHITECTURE.md §6.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from orchestrator.application.rules.run_label import (
    MAX_LABEL,
    clean_label,
    default_label,
    initial_label,
)
from orchestrator.domain.errors import Invalid

AT = datetime(2026, 11, 10, 10, 23, 41, tzinfo=UTC)


def test_the_default_names_project_folder_template_and_utc_minute() -> None:
    label = default_label(
        "familio", {"initiative_folder": "initiatives/familio-snake-v2"}, "bench-v1-staged", AT
    )

    assert label == "familio familio-snake-v2 bench-v1-staged 2026-11-10 10:23"


def test_without_a_folder_the_word_is_dropped() -> None:
    assert default_label("familio", {}, "repo-init", AT) == "familio repo-init 2026-11-10 10:23"


def test_a_spec_folder_with_a_trailing_slash_gives_its_last_segment() -> None:
    label = default_label("p", {"spec_folder": "specs/x/"}, "t", AT)

    assert label == "p x t 2026-11-10 10:23"


def test_the_initiative_folder_wins_over_the_spec_folder() -> None:
    inputs = {"initiative_folder": "a/b", "spec_folder": "c/d"}

    assert default_label("p", inputs, "t", AT) == "p b t 2026-11-10 10:23"


@pytest.mark.parametrize("value", [None, 3, "", "/"])
def test_a_folder_that_is_not_a_usable_string_is_ignored(value: object) -> None:
    inputs = {"initiative_folder": value, "spec_folder": "specs/y"}
    expected = "p t 2026-11-10 10:23" if value == "/" else "p y t 2026-11-10 10:23"
    if value == "/":
        inputs = {"initiative_folder": value}

    assert default_label("p", inputs, "t", AT) == expected


def test_a_non_utc_time_is_converted() -> None:
    at = datetime(2026, 11, 10, 23, 30, tzinfo=timezone(timedelta(hours=2)))

    assert default_label("p", {}, "t", at) == "p t 2026-11-10 21:30"


def test_an_empty_project_name_is_dropped() -> None:
    assert default_label("", {}, "t", AT) == "t 2026-11-10 10:23"


def test_clean_label_trims_and_bounds() -> None:
    assert clean_label("  snake round 2  ") == "snake round 2"
    assert clean_label("a") == "a"
    assert clean_label("a" * MAX_LABEL) == "a" * MAX_LABEL


@pytest.mark.parametrize("text", ["", "   ", "a" * (MAX_LABEL + 1)])
def test_clean_label_refuses_empty_and_long(text: str) -> None:
    with pytest.raises(Invalid):
        clean_label(text)


def test_initial_label_uses_the_given_text_as_the_operators() -> None:
    assert initial_label(" mine ", "p", {}, "t", AT) == ("mine", True)


def test_initial_label_falls_back_to_the_default() -> None:
    assert initial_label(None, "p", {}, "t", AT) == ("p t 2026-11-10 10:23", False)
