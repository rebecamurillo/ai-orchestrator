"""The `metrics.analyse` kind as the registry's consumers see it: validate, plan (epic 5 story 4).

The Template here is the test's own fixture; the shipped `templates/*.yaml` are never read
(hard rule 6).
"""

from __future__ import annotations

from orchestrator.application.steps import ANALYSE_KIND, KIND_META
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import ResolvedTree
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.templates import FakeTemplateVersionRepository

ANALYSING = """name: analysing
version: 1
inputs:
  project:           { type: project,    required: true }
  repository:        { type: repository, required: true }
  base_branch:       { type: string,     required: true }
  branch:            { type: string,     required: true }
  initiative_folder: { type: path,       required: true }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}", mode: attach }
    gate: deterministic
  - id: epics
    for_each: "{{initiative_folder}}/epics.yaml"
    as: epic
    steps:
      - id: setup
        role: deterministic
        run: "{{repository.install_command}}"
        gate: deterministic
  - id: metrics
    role: deterministic
    uses: metrics.analyse
"""


def _validated():  # type: ignore[no-untyped-def]
    return validate(ANALYSING, templates=FakeTemplateVersionRepository([]))


def test_the_kind_has_no_gate_default_no_timeout_and_no_with_key() -> None:
    meta = KIND_META[ANALYSE_KIND]

    assert (meta.gate_default, meta.timeout_default_min, meta.with_keys) == (
        None,
        None,
        frozenset(),
    )
    assert meta.planner_only is False


def test_a_template_ending_with_the_row_validates_and_reports_it_unvalidated() -> None:
    result = _validated()

    assert result.errors == ()
    assert result.unvalidated == ("metrics",)


def test_the_plans_last_row_is_the_analyse_row_with_gate_unvalidated() -> None:
    result = _validated()
    assert result.template is not None
    plan = plan_run(
        ResolvedTree(root=result.template, callees=()),
        fixtures.inputs(
            values={"branch": "feat/fresh", "initiative_folder": fixtures.INITIATIVE_FOLDER}
        ),
        git=fixtures.initiative_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )

    last = plan.rows[-1]
    assert (last.path, last.kind, last.gate) == ("metrics", ANALYSE_KIND, "unvalidated")
