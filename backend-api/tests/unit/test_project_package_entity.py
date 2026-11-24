"""The project_package entities (story 3 of epic 6)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.domain.entities.project_package import (
    GateWords,
    PackageDeclaration,
    SequenceEntry,
    StepDecl,
)
from orchestrator.domain.entities.template import TemplateVersion


def declaration() -> PackageDeclaration:
    step = StepDecl(id="a", kind="conversation", skill="s", persona="p", file="f", writes=("x",))
    return PackageDeclaration(
        name="pkg",
        sequence=(
            SequenceEntry(
                workflow="spec",
                template="pkg.spec",
                version=1,
                type="interactive",
                shown_as="workflow",
                steps=(step,),
            ),
        ),
        gate=GateWords(pass_words=("pass",), fail_words=("fail",), owners_key="owners"),
        status_map={"final": "done"},
    )


def test_the_models_are_frozen() -> None:
    with pytest.raises(ValidationError):
        declaration().name = "other"  # type: ignore[misc]


def test_a_template_version_without_package_sha_reads_none() -> None:
    assert TemplateVersion(name="n", version=1, yaml="", hash="h").package_sha is None


def test_the_declaration_round_trips_through_json() -> None:
    original = declaration()

    again = PackageDeclaration.model_validate(original.model_dump(mode="json"))

    assert again == original
