"""Planner verification for the hub-Run templates' own design choices (H3, 2026-09-23).

The shipped `templates/initiative-hub*.yaml` files are exemplars and are never pinned by a
test (hard rule 6) — `test_shipped_smoke.py` covers the invariants that must hold of *any*
text the shipped directory carries. What is pinned here is the *mechanism* H3's templates
were written to rely on, on fixture Templates this module owns:

- an `epics.yaml` entry that leaves a command field out (or leaves it blank) must plan that
  callee's `run:` row `skipped · no command` — which is what makes the field optional at
  all, and is why `initiative-hub-epic.yaml`'s steps read the bare field (`run: "{{install}}"`)
  and never build the command themselves (`run: "cd {{workdir}} && {{install}}"`, demonstrated
  below as the shape that does *not* skip cleanly);
- a `for_each` callee bound to `{{epic.workdir}}` (an item field, not a whole variable) reads
  it as a plain string at plan time, which is what lets a `string`-typed callee input accept
  one at all (`calls.py::_binds`'s `TEXT_BINDABLE` fallback).
"""

from __future__ import annotations

from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import Plan, ResolvedTree
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateVersion
from orchestrator.domain.values import PlannedRow
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

BASE_BRANCH = fixtures.BASE_BRANCH
INITIATIVE_BRANCH = "feat/initiative-x"
INITIATIVE_FOLDER = "docs/initiative"
EPICS_PATH = f"{INITIATIVE_FOLDER}/epics.yaml"
BASE_SHA = fixtures.BASE_SHA

#: The callee: one `run:` row reading the bare field (H3's chosen convention), and one
#: reading the `cd {{workdir}} && {{install}}` shape H3's authors rejected — kept here only
#: to prove *why* it was rejected, never shipped.
CALLEE = """name: hub-epic-fixture
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  branch:      { type: string,     required: true }
  workdir:     { type: string,     required: true }
  install:     { type: string,     required: false }
steps:
  - id: branch
    uses: git.submodule
    with: { workdir: "{{workdir}}", branch: "{{branch}}", base: "{{base_branch}}" }
    gate: deterministic
  - id: setup
    run: "{{install}}"
    gate: deterministic
  - id: antipattern
    run: "cd {{workdir}} && {{install}}"
    gate: deterministic
"""

#: The root: one `for_each` over an `epics.yaml`, calling the callee above with the item's
#: own `workdir`/`install` fields — the same shape `initiative-hub.yaml` uses.
ROOT = """name: hub-fixture
version: 1
inputs:
  project:           { type: project,    required: true }
  repository:        { type: repository, required: true }
  base_branch:        { type: string,     required: true }
  branch:              { type: string,     required: true }
  initiative_folder:  { type: path,       required: true }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}", mode: attach }
    gate: deterministic
  - id: epics
    for_each: "{{initiative_folder}}/epics.yaml"
    as: epic
    steps:
      - id: epic
        uses: template
        with:
          name: hub-epic-fixture
          version: 1
          inputs:
            project: "{{project}}"
            repository: "{{repository}}"
            base_branch: "{{base_branch}}"
            branch: "{{branch}}"
            workdir: "{{epic.workdir}}"
            install: "{{epic.install}}"
"""

#: Three epics: a normal command, one whose entry leaves `install` out entirely, and one
#: whose entry states it blank — `lists.py::REQUIRED_FIELDS[EPICS_KIND]` still applies
#: (`id`, `title`, `branch`, `spec_folder`), whatever the hub-Run fields on top of it.
EPICS = """
- id: e1
  title: The first epic
  branch: unused-by-the-hub-flow
  spec_folder: epic-1
  workdir: repos/api
  install: "cd repos/api && yarn install"
- id: e2
  title: The second epic
  branch: unused-by-the-hub-flow
  spec_folder: epic-2
  workdir: repos/web
- id: e3
  title: The third epic
  branch: unused-by-the-hub-flow
  spec_folder: epic-3
  workdir: repos/worker
  install: "   "
"""


def _tree() -> ResolvedTree:
    callee = validate(CALLEE, templates=FakeTemplateVersionRepository())
    assert callee.template is not None, callee.errors
    stored = FakeTemplateVersionRepository(
        [TemplateVersion(name="hub-epic-fixture", version=1, yaml=CALLEE, hash="sha")]
    )
    result = validate(ROOT, templates=stored)
    assert result.template is not None, result.errors
    return ResolvedTree(root=result.template, callees=(callee.template,))


def _plan() -> Plan:
    git = FakeGit(
        refs={BASE_BRANCH: BASE_SHA},
        files={(BASE_SHA, EPICS_PATH): EPICS},
        listings={},
    )
    return plan_run(
        _tree(),
        fixtures.inputs(
            values={"branch": INITIATIVE_BRANCH, "initiative_folder": INITIATIVE_FOLDER}
        ),
        git=git,
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )


def _row(plan: Plan, path: str) -> PlannedRow:
    return next(entry for entry in plan.rows if entry.path == path)


def test_the_fixture_root_and_callee_validate_clean() -> None:
    tree = _tree()

    assert tree.root.name == "hub-fixture"
    assert [callee.name for callee in tree.callees] == ["hub-epic-fixture"]


# --- (b): an item field binds into a string-typed callee input as a plain string -----------


def test_an_item_field_binds_into_the_callees_string_input_as_the_entrys_own_value() -> None:
    plan = _plan()

    assert _row(plan, "epics[0].branch").with_resolved["workdir"] == "repos/api"
    assert _row(plan, "epics[1].branch").with_resolved["workdir"] == "repos/web"


# --- (a): an unbound (or blank) item field empties a `run:` row, whitespace included -------


def test_a_command_field_the_entry_states_skips_no_such_row() -> None:
    setup = _row(_plan(), "epics[0].setup")

    assert setup.status == "planned"
    assert setup.with_resolved["command"] == "cd repos/api && yarn install"


def test_a_command_field_the_entry_omits_plans_a_skipped_row_never_an_error() -> None:
    setup = _row(_plan(), "epics[1].setup")

    assert (setup.status, setup.reason) == ("skipped", "no command")


def test_a_whitespace_only_command_field_skips_the_same_way_as_an_absent_one() -> None:
    setup = _row(_plan(), "epics[2].setup")

    assert (setup.status, setup.reason) == ("skipped", "no command")


# --- why the rejected `cd {{workdir}} && {{install}}` shape was rejected -------------------


def test_prefixing_the_command_with_cd_defeats_the_empty_check_the_chosen_shape_relies_on() -> None:
    """The whole reason H3's templates read the bare field: `cd repos/web && ` is not blank
    once whitespace is stripped, so a row built this way would run a bare `cd` as a Story's
    verify command instead of being skipped — demonstrated here and never shipped."""
    antipattern = _row(_plan(), "epics[1].antipattern")

    assert antipattern.status == "planned"
    assert antipattern.with_resolved["command"] == "cd repos/web && "
