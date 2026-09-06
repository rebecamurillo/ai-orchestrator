"""`FakeTemplateVersionRepository` — the one in-memory `TemplateVersionRepository` (AD-18).

It stands in for a table whose primary key is `(name, version)` and whose rows are frozen
once pinned, so it refuses what that table would refuse. A fake that quietly replaced a
stored version would let a caller that never checked pass here and fail on the first insert.
"""

from __future__ import annotations

import pytest

from orchestrator.domain.entities.template import TemplateVersion
from tests.unit.fakes.templates import FakeTemplateVersionRepository

BODY = "name: story\nversion: 1\nsteps: []\n"


def a_version(name: str = "story", number: int = 1) -> TemplateVersion:
    return TemplateVersion(name=name, version=number, yaml=BODY, hash="sha")


def test_an_added_version_is_found_by_name_and_number() -> None:
    version = a_version()
    templates = FakeTemplateVersionRepository([version])

    assert templates.get("story", 1) == version


def test_what_is_not_stored_is_none_rather_than_an_error() -> None:
    assert FakeTemplateVersionRepository().get("story", 1) is None


def test_a_different_number_of_the_same_template_is_a_different_version() -> None:
    templates = FakeTemplateVersionRepository([a_version(number=1), a_version(number=2)])

    assert templates.get("story", 2) is not None
    assert templates.get("story", 3) is None


def test_two_templates_may_share_a_version_number() -> None:
    templates = FakeTemplateVersionRepository([a_version(), a_version(name="epic")])

    assert templates.get("epic", 1) is not None


def test_storing_the_same_version_twice_is_refused_as_the_primary_key_would_refuse_it() -> None:
    templates = FakeTemplateVersionRepository([a_version()])

    with pytest.raises(ValueError, match="story@1"):
        templates.add(a_version())


def test_the_store_starts_empty() -> None:
    assert FakeTemplateVersionRepository().versions == {}
