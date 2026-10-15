"""The e2e suite's own workflow Templates (`tests/e2e/templates/`), read as files.

Operator ruling (2026-10-15): no test depends on the shipped `templates/*.yaml` — the e2e
suite posts these fixtures instead. Two facts about them are checkable without a stack, and
are checked here so a fixture edit that breaks them fails `make test` before `make e2e`:

- every fixture validates under the one parser (`application/templates/validate.py`), with
  its callees resolved the way the suite saves them — leaf first;
- every `skill:` an agent row names is an internal one, a directory of `ia-agents-skills/`,
  because that is all the gate's stack ever installs: a BMAD stub exists only inside the
  built image, and a from-source backend (the `e2e-api` job) refuses a Run that would
  dispatch a skill its catalog cannot resolve.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateCallRef, TemplateVersion
from tests.e2e.helpers import templates as fixtures
from tests.unit.fakes.templates import FakeTemplateVersionRepository

REPO_ROOT = Path(__file__).resolve().parents[3]
INTERNAL_SKILLS_DIR = REPO_ROOT / "ia-agents-skills"

#: Each fixture with the tokens it takes, in the order the suite saves them: a callee before
#: every caller that follows it, under the name the caller's token is filled with.
CHAIN: tuple[tuple[str, dict[str, str]], ...] = (
    (fixtures.STORY, {}),
    (fixtures.EPIC, {"STORY": "story"}),
    (fixtures.HUB_STORY, {}),
    (fixtures.HUB_EPIC, {"STORY": "hub-story"}),
    (fixtures.HUB, {"EPIC": "hub-epic"}),
    (fixtures.REPO_INIT, {}),
)


def stem(file: str) -> str:
    return file.removesuffix(".yaml")


def internal_skills() -> frozenset[str]:
    return frozenset(path.name for path in INTERNAL_SKILLS_DIR.iterdir() if path.is_dir())


def agent_skills(document: object) -> list[str]:
    """Every `skill:` under a `uses: agent` row, however deep the step tree nests."""
    found: list[str] = []
    if isinstance(document, dict):
        if document.get("uses") == "agent":
            skill = (document.get("with") or {}).get("skill")
            if skill is not None:
                found.append(str(skill))
        for value in document.values():
            found.extend(agent_skills(value))
    elif isinstance(document, list):
        for item in document:
            found.extend(agent_skills(item))
    return found


@pytest.fixture(scope="module")
def stored() -> FakeTemplateVersionRepository:
    """Every fixture validated and stored in chain order, so each caller resolves its
    callee exactly as the stack does once the suite has posted the leaf."""
    repository = FakeTemplateVersionRepository()
    for file, callees in CHAIN:
        text = fixtures.fixture_text(file, NAME=stem(file), **callees)
        result = validate(text, templates=repository)
        assert result.errors == (), (file, result.errors)
        repository.add(
            TemplateVersion(
                name=stem(file),
                version=1,
                yaml=text,
                hash="sha",
                calls=tuple(
                    TemplateCallRef(name=callee, version=None) for callee in callees.values()
                ),
            )
        )
    return repository


def test_the_chain_names_every_fixture_file_once() -> None:
    on_disk = sorted(path.name for path in fixtures.TEMPLATES_DIR.glob("*.yaml"))
    assert on_disk == sorted(file for file, _ in CHAIN)


@pytest.mark.parametrize(("file", "callees"), CHAIN, ids=[file for file, _ in CHAIN])
def test_every_fixture_validates_with_no_unvalidated_step(
    stored: FakeTemplateVersionRepository, file: str, callees: dict[str, str]
) -> None:
    text = fixtures.fixture_text(file, NAME=stem(file), **callees)

    result = validate(text, templates=stored)

    assert result.errors == ()
    assert result.template is not None
    assert result.unvalidated == ()


@pytest.mark.parametrize(("file", "callees"), CHAIN, ids=[file for file, _ in CHAIN])
def test_every_agent_row_dispatches_an_internal_skill(file: str, callees: dict[str, str]) -> None:
    document = yaml.safe_load(fixtures.fixture_text(file, NAME=stem(file), **callees))

    skills = agent_skills(document)

    # a pure caller (`hub.yaml`) names none; every name a fixture does carry is internal
    assert set(skills) <= internal_skills(), (file, sorted(set(skills) - internal_skills()))
    assert not [skill for skill in skills if skill.startswith("bmad-")]


def test_an_unfilled_token_is_a_named_failure_not_yaml_the_stack_rejects() -> None:
    with pytest.raises(pytest.fail.Exception, match="STORY"):
        fixtures.fixture_text(fixtures.EPIC, NAME="epic")
