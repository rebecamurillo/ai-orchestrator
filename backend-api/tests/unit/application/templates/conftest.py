"""The stored Template Versions every call test resolves against.

One fake, the shared one (AD-18). The bodies are the fixture files, so a callee's declared
inputs are read out of a file a reader can open rather than out of a string in a test.
"""

from __future__ import annotations

import pytest

from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from tests.unit.application.templates import fixture
from tests.unit.fakes.templates import FakeTemplateVersionRepository

TRIVIAL = (
    "name: leaf\nversion: 1\nsteps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
)


def version(name: str, number: int, body: str, *calls: TemplateRef) -> TemplateVersion:
    return TemplateVersion(name=name, version=number, yaml=body, hash="sha", calls=calls)


@pytest.fixture
def templates() -> FakeTemplateVersionRepository:
    """`story@1`, `story@2`, `strict@1`, and the chains the depth and cycle rules need."""
    return FakeTemplateVersionRepository(
        [
            version("story", 1, fixture("callee-story")),
            version("story", 2, fixture("callee-story-full")),
            version("strict", 1, fixture("callee-strict")),
            # initiative -> epic -> story: three templates, the deepest chain allowed
            version("epic", 1, TRIVIAL, TemplateRef(name="story", version=1)),
            # a -> b -> c -> d: four, one too many
            version("b", 1, TRIVIAL, TemplateRef(name="c", version=1)),
            version("c", 1, TRIVIAL, TemplateRef(name="d", version=1)),
            version("d", 1, TRIVIAL),
            # a -> cycle-b -> a: back to the root the descent started from
            version("cycle-b", 1, TRIVIAL, TemplateRef(name="a", version=1)),
        ]
    )
