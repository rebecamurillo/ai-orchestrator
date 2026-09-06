"""`TemplateVersion.id`/`created_at` and `TemplateSummary` — 3.3's entity extension.

3.1's fixtures build a `TemplateVersion` with neither field; this module is where the two
new ones are pinned: both default to `None`, and a real save (`use_cases/templates.py`)
always supplies both before a version reaches a repository.
"""

from __future__ import annotations

from datetime import UTC, datetime

from orchestrator.domain.entities.template import TemplateRef, TemplateSummary, TemplateVersion
from orchestrator.domain.ids import new_id

AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)

#: The summary test's own latest version, named so the comparison names no magic number.
LATEST_VERSION = 2

BODY = "name: story\nversion: 1\nsteps: []\n"


def test_id_defaults_to_none_for_a_fixture_that_never_stores_the_version() -> None:
    version = TemplateVersion(name="story", version=1, yaml=BODY, hash="sha")

    assert version.id is None


def test_created_at_defaults_to_none_for_the_same_reason() -> None:
    version = TemplateVersion(name="story", version=1, yaml=BODY, hash="sha")

    assert version.created_at is None


def test_a_real_save_carries_both() -> None:
    identifier = new_id()
    version = TemplateVersion(
        id=identifier, name="story", version=1, yaml=BODY, hash="sha", created_at=AT
    )

    assert version.id == identifier
    assert version.created_at == AT


def test_ref_is_unaffected_by_the_new_fields() -> None:
    version = TemplateVersion(
        id=new_id(), name="epic", version=3, yaml=BODY, hash="sha", created_at=AT
    )

    assert version.ref() == TemplateRef(name="epic", version=3)


# --- TemplateSummary -----------------------------------------------------------------------


def test_a_summary_carries_its_name_description_and_versions() -> None:
    summary = TemplateSummary(
        name="epic", description="the epic loop", latest_version=2, versions=(1, 2)
    )

    assert summary.name == "epic"
    assert summary.description == "the epic loop"
    assert summary.latest_version == LATEST_VERSION
    assert summary.versions == (1, 2)


def test_a_summary_may_carry_no_description() -> None:
    summary = TemplateSummary(name="repo-init", latest_version=1, versions=(1,))

    assert summary.description is None


def test_a_summary_defaults_to_no_versions() -> None:
    summary = TemplateSummary(name="story", latest_version=1)

    assert summary.versions == ()
