"""`FakeTemplateVersionRepository`'s writes (3.3): `add_version`, `list`, `list_versions`,
`callers_of`. The reads `get`/`add` stay pinned by `test_template_fake.py` (3.1); this
module is where the extension lands, so both stay green from the story that added them.
"""

from __future__ import annotations

import pytest

from orchestrator.domain.entities.template import (
    TemplateCaller,
    TemplateCallRef,
    TemplateRef,
    TemplateVersion,
)
from orchestrator.domain.ports.templates import TemplateVersionRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

BODY = "name: story\nversion: 1\nsteps: []\n"

#: `story` ends up with two saved versions in the list-grouping test below.
STORY_LATEST_VERSION = 2


def a_version(name: str = "story", number: int = 1, **overrides: object) -> TemplateVersion:
    fields: dict[str, object] = {"name": name, "version": number, "yaml": BODY, "hash": "sha"}
    fields.update(overrides)
    return TemplateVersion(**fields)  # type: ignore[arg-type]


def test_the_extended_fake_still_satisfies_the_port() -> None:
    templates: TemplateVersionRepository = FakeTemplateVersionRepository()

    assert isinstance(templates, TemplateVersionRepository)


def test_add_version_stores_the_version_like_add() -> None:
    templates = FakeTemplateVersionRepository()

    templates.add_version(a_version(), description=None)

    assert templates.get("story", 1) is not None


def test_add_version_refuses_a_pair_already_stored() -> None:
    templates = FakeTemplateVersionRepository([a_version()])

    with pytest.raises(ValueError, match="story@1"):
        templates.add_version(a_version(), description=None)


def test_add_version_records_the_names_description() -> None:
    templates = FakeTemplateVersionRepository()

    templates.add_version(a_version(), description="the story loop")

    assert templates.descriptions["story"] == "the story loop"


def test_list_reports_one_row_per_name_with_its_latest_description() -> None:
    templates = FakeTemplateVersionRepository()
    templates.add_version(a_version(number=1), description="v1 text")
    templates.add_version(a_version(number=2), description="v2 text")
    templates.add_version(a_version(name="epic", number=1), description="epic text")

    summaries = {summary.name: summary for summary in templates.list()}

    assert summaries["story"].versions == (1, 2)
    assert summaries["story"].latest_version == STORY_LATEST_VERSION
    assert summaries["story"].description == "v2 text"
    assert summaries["epic"].versions == (1,)


def test_list_is_empty_when_nothing_is_stored() -> None:
    assert FakeTemplateVersionRepository().list() == []


def test_list_versions_is_ascending_and_scoped_to_the_name() -> None:
    templates = FakeTemplateVersionRepository(
        [a_version(number=2), a_version(number=1), a_version(name="epic", number=1)]
    )

    assert templates.list_versions("story") == [1, 2]


def test_list_versions_is_empty_for_an_unknown_name() -> None:
    assert FakeTemplateVersionRepository().list_versions("nothing") == []


def test_callers_of_finds_every_version_whose_calls_names_the_target() -> None:
    templates = FakeTemplateVersionRepository(
        [
            a_version(name="story", number=1),
            a_version(name="epic", number=1, calls=(TemplateRef(name="story", version=1),)),
            a_version(name="initiative", number=1, calls=(TemplateRef(name="epic", version=1),)),
        ]
    )

    # revised to `TemplateCaller` by the Operator decision 2026-10-02, editable workflows: a
    # `uses: template` call may omit `version`; it resolves to the callee's latest at validate
    # and plan time; no cascade.
    assert templates.callers_of("story", 1) == [TemplateCaller(name="epic", version=1, pinned=True)]
    assert templates.callers_of("epic", 1) == [
        TemplateCaller(name="initiative", version=1, pinned=True)
    ]


def test_callers_of_counts_an_unpinned_caller_against_every_version_of_the_callee() -> None:
    templates = FakeTemplateVersionRepository(
        [
            a_version(name="story", number=1),
            a_version(name="story", number=2),
            a_version(name="epic", number=1, calls=(TemplateCallRef(name="story", version=None),)),
            a_version(name="old", number=1, calls=(TemplateRef(name="story", version=1),)),
        ]
    )

    assert templates.callers_of("story", 1) == [
        TemplateCaller(name="epic", version=1, pinned=False),
        TemplateCaller(name="old", version=1, pinned=True),
    ]
    assert templates.callers_of("story", 2) == [
        TemplateCaller(name="epic", version=1, pinned=False)
    ]
    assert templates.callers_of("story", 3) == [
        TemplateCaller(name="epic", version=1, pinned=False)
    ]


def test_callers_of_is_empty_for_a_version_nothing_calls() -> None:
    templates = FakeTemplateVersionRepository([a_version()])

    assert templates.callers_of("story", 1) == []
