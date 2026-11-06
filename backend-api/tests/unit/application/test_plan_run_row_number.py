"""A stored version's number is its row, whatever its text's `version:` line says.

Story 1 of the template-folder epic (SPEC CAP-1; D12, 2026-11-06): a Run pins the version
it actually ran, so resolving, pinning and reporting plan errors use the stored row number.
Every stored text here says `version: 1` while its row is higher, so these tests fail on a
planner that reads the text.
"""

from __future__ import annotations

import pytest

from orchestrator.application.templates.plan_model import PlanError
from orchestrator.application.use_cases.plan_run import PlanPorts, plan_for, resolve_tree
from orchestrator.domain.entities.template import TemplateCallRef, TemplateRef, TemplateVersion
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

CALLEE = fixtures.TEXTS["story"]
ROW = 3

_CALL = """  - id: {id}
    uses: template
    with:
      name: story
{version}      inputs:
        project: "{{{{project}}}}"
        repository: "{{{{repository}}}}"
        branch: "{{{{branch}}}}"
        spec_folder: "{{{{spec_folder}}}}"
        story: "{{{{story}}}}"
"""

_HEAD = """name: r
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  branch:      { type: string,     required: true }
  spec_folder: { type: path,       required: true }
  story:       { type: item,       required: true }
steps:
"""


def _root(*versions: int | None) -> str:
    calls = [
        _CALL.format(id=f"call{index}", version="" if v is None else f"      version: {v}\n")
        for index, v in enumerate(versions)
    ]
    return _HEAD + "".join(calls)


def _store(
    root_text: str, *, calls: tuple[TemplateRef | TemplateCallRef, ...]
) -> FakeTemplateVersionRepository:
    return FakeTemplateVersionRepository(
        [
            TemplateVersion(name="story", version=1, yaml=CALLEE, hash="s1"),
            TemplateVersion(name="r", version=2, yaml=root_text, hash="r2", calls=calls),
            TemplateVersion(name="story", version=ROW, yaml=CALLEE, hash="s3"),
        ]
    )


R2 = TemplateRef(name="r", version=2)


def test_an_unpinned_callee_is_pinned_and_found_at_its_row_not_its_text() -> None:
    store = _store(_root(None), calls=(TemplateCallRef(name="story", version=None),))

    tree = resolve_tree(store, R2)

    assert [(p.name, p.version) for p in tree.pinned_versions()] == [("r", 2), ("story", ROW)]
    assert tree.latest == {"story": ROW}
    found = tree.callee("story", None)
    assert found is not None
    assert found.version == ROW


def test_a_pinned_callee_is_found_and_pinned_at_its_row() -> None:
    store = _store(_root(ROW), calls=(TemplateRef(name="story", version=ROW),))

    tree = resolve_tree(store, R2)

    found = tree.callee("story", ROW)
    assert found is not None
    assert found.version == ROW
    assert [(p.name, p.version) for p in tree.pinned_versions()] == [("r", 2), ("story", ROW)]
    assert tree.latest == {}


def test_a_plan_error_inside_a_version_names_its_row() -> None:
    versions = fixtures.repository_of_versions()
    versions.add(
        TemplateVersion(
            name="epic",
            version=ROW,
            yaml=fixtures.TEXTS["epic"],
            hash="e3",
            calls=(TemplateRef(name="story", version=1),),
        )
    )
    git = FakeGit(
        refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA, fixtures.EPIC_BRANCH: fixtures.WORK_SHA},
        files={
            (fixtures.WORK_SHA, f"{fixtures.SPEC_FOLDER}/stories.yaml"): '- id: "1"\n',
        },
        listings={},
    )

    with pytest.raises(PlanError) as raised:
        plan_for(
            PlanPorts(templates=versions, git=git),
            TemplateRef(name="epic", version=ROW),
            fixtures.epic_inputs(),
            base_dir=fixtures.BASE,
            bmad_version=fixtures.BMAD_VERSION,
        )

    assert raised.value.version == ROW
    assert "epic@3" in str(raised.value)


def test_a_callee_reached_pinned_then_unpinned_at_one_row_is_listed_once_and_in_latest() -> None:
    store = _store(
        _root(ROW, None),
        calls=(TemplateRef(name="story", version=ROW), TemplateCallRef(name="story", version=None)),
    )

    tree = resolve_tree(store, R2)

    assert [(c.name, c.version) for c in tree.callees] == [("story", ROW)]
    assert tree.latest == {"story": ROW}
    assert tree.callee("story", ROW) is tree.callees[0]
    assert tree.callee("story", None) is tree.callees[0]
