"""The `writes` agent extra: what a Template may declare a dispatch will write (AD-17).

AD-17 makes `SPEC.md`, `stories.yaml`, `epics.yaml`, every `AGENTS.md` and every frozen test
file read-only to an agent — to an agent *that was not sent there*. A dispatch whose whole
purpose is to write one of them is not the case the rule is about, and before this key there
was no way for a Template to say so: `repo-init@1`'s `context` step runs
`bmad-project-context`, whose only output is the repository's `AGENTS.md`, and every Run of
it would have parked on the file the Operator asked for.

Asserted here: the key's shape is checked the way `expect.files` is, and the planner resolves
it onto the row like every other agent extra — through `plan_run`, because a rule that only
holds when the extras function is called by hand is not a rule about plans.

What the rule does with it is `tests/unit/application/test_declared_writes_rule.py`'s; the
executor wiring is `tests/unit/application/steps/test_agent_declared_writes.py`'s.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.templates.model import INVALID_VALUE, ParsedTemplate
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import Plan, ResolvedTree
from orchestrator.application.templates.table import WRITES_KEY
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

FOLDER = "docs/epic-1"
REF = fixtures.BASE_SHA

HEAD = """name: writes
version: 1
description: one dispatch, and what it was sent to write
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  spec_folder: { type: path,       required: true }
steps:
  - id: work
    uses: agent
    gate: liveness
"""


def errors_of(declaration: str) -> tuple[str, ...]:
    result = validate(HEAD + declaration, templates=FakeTemplateVersionRepository([]))
    return tuple(error.reason for error in result.errors)


def _parsed(text: str) -> ParsedTemplate:
    result = validate(text, templates=FakeTemplateVersionRepository([]))
    assert result.template is not None, result.errors
    return result.template


def planned(declaration: str) -> Plan:
    return plan_run(
        ResolvedTree(root=_parsed(HEAD + declaration)),
        fixtures.inputs(values={"spec_folder": FOLDER}),
        git=FakeGit(refs={fixtures.BASE_BRANCH: REF}, files={}, listings={}),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )


def resolved(declaration: str) -> dict[str, Any]:
    return next(row for row in planned(declaration).rows if row.path == "work").with_resolved


# ── the shape: the boundary `expect.files` is held to ───────────────────────


def test_a_list_of_paths_is_accepted() -> None:
    assert errors_of('    writes: ["AGENTS.md", "web-client/AGENTS.md"]\n') == ()


def test_a_path_that_is_not_text_is_not_a_path() -> None:
    assert errors_of("    writes: [3]\n") == (INVALID_VALUE,)


def test_a_list_of_offences_is_one_problem_at_the_keys_own_line() -> None:
    """Every entry is reported at the `writes:` line, and `validate` keeps one problem per
    line and reason — so a list of four numbers is one thing to fix, not four."""
    assert errors_of("    writes: [3, 4]\n") == (INVALID_VALUE,)


def test_a_value_that_is_not_a_list_at_all_is_refused() -> None:
    assert errors_of('    writes: "AGENTS.md"\n') == (INVALID_VALUE,)


def test_the_key_belongs_to_the_agent_kind_and_no_other() -> None:
    """A `git.commit` step that declares one is an unknown key, not a second rule."""
    text = HEAD.replace("uses: agent", "uses: git.commit") + '    writes: ["AGENTS.md"]\n'

    assert (
        errors_of("") == ()
        and validate(text, templates=FakeTemplateVersionRepository([])).errors != ()
    )


# ── what the plan carries ───────────────────────────────────────────────────


def test_the_declared_paths_reach_the_row_in_file_order() -> None:
    assert resolved('    writes: ["b.md", "a.md"]\n')[WRITES_KEY] == ["b.md", "a.md"]


def test_a_row_whose_step_declared_none_carries_the_empty_list() -> None:
    """The rule reads one key and never has to ask whether the row has it."""
    assert resolved("")[WRITES_KEY] == []


def test_a_declared_path_is_substituted_like_every_other_resolved_value() -> None:
    """AD-7: the plan decides before anything starts, so `{{…}}` is filled in here."""
    assert resolved('    writes: ["{{spec_folder}}/AGENTS.md"]\n')[WRITES_KEY] == [
        f"{FOLDER}/AGENTS.md"
    ]
