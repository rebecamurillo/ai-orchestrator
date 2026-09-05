"""The `TemplateVersion` entity and the `TemplateVersionRepository` port (AD-15, AD-18).

The port is read-only in this story: a validator resolves a callee, and 3.3 adds the writes
that create version n+1. What is checked here is the shape a use case is entitled to assume
— that the fake satisfies the Protocol structurally, that a version is immutable, and that
"not stored" is `None` rather than an error.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from orchestrator.domain.ports.templates import TemplateVersionRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

BODY = "name: story\nversion: 1\nsteps: []\n"


def a_version(**overrides: object) -> TemplateVersion:
    fields: dict[str, object] = {
        "name": "story",
        "version": 1,
        "yaml": BODY,
        "hash": "0f" * 32,
    }
    fields.update(overrides)
    return TemplateVersion(**fields)  # type: ignore[arg-type]


def test_the_fake_satisfies_the_port() -> None:
    templates: TemplateVersionRepository = FakeTemplateVersionRepository()

    assert isinstance(templates, TemplateVersionRepository)


def test_a_version_carries_its_text_its_digest_and_the_callees_it_pins() -> None:
    version = a_version(calls=(TemplateRef(name="epic", version=2),))

    assert version.yaml == BODY
    assert version.calls == (TemplateRef(name="epic", version=2),)


def test_a_version_pins_nothing_by_default() -> None:
    assert a_version().calls == ()


def test_a_version_is_frozen_because_a_pinned_version_never_changes() -> None:
    version = a_version()

    with pytest.raises(PydanticValidationError):
        version.version = 2  # type: ignore[misc]


def test_a_reference_is_frozen_too() -> None:
    ref = TemplateRef(name="story", version=1)

    with pytest.raises(PydanticValidationError):
        ref.name = "epic"  # type: ignore[misc]


def test_a_version_names_itself_as_a_reference() -> None:
    assert a_version(name="epic", version=3).ref() == TemplateRef(name="epic", version=3)


def test_two_references_to_the_same_version_are_equal() -> None:
    assert TemplateRef(name="story", version=1) == TemplateRef(name="story", version=1)
