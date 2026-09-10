"""A dispatch with no Story behind it, planned and then executed (FR-16, AD-7).

Every `agent` row in the unit suite until now was a Story's: a Spec folder, a list entry, a
Story file to write. `repo-init@1`'s `context` step is the first that is none of those — it
runs a skill against the repository itself — and the gap between the two shapes is what this
module holds shut.

**The defect this was written for.** `agent_row.agent_extras` wrote an `expect` contract onto
*every* agent row, so a row that declared none was indistinguishable from one that declared
an empty one. `agent_tail._globs` then filled FR-16's own glob from the blanks such a row
carries — `{spec_folder}/stories/{story_id}-*.md` with both empty — and asked the Workspace
for `/stories/-*.md`, an absolute path it rightly refuses as outside its root. The executor
raised instead of routing and the Run parked `internal`: a dispatch that had done nothing
wrong, stopped by a contract nobody wrote. `tail` has always had the branch for a row with no
contract (`files is None` → report what was observed); the row simply never reached it.

Asserted at both levels, because either alone would have missed it: the plan must not invent
a contract, and the executor must survive the row the plan really writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.templates.agent_row import EXPECT_KEY, RETRY_KEY
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import Plan, ResolvedTree
from orchestrator.application.templates.validate import validate
from tests.unit.application.steps.agent_tail_fixtures import LOG_PATH, a_tail_world
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.templates import FakeTemplateVersionRepository

#: `templates/repo-init.yaml`, off disk — the same text the shipped-template suite reads, so
#: this cannot pass against a Template that no longer has the step it is about.
REPO_ROOT = Path(__file__).resolve().parents[5]
TEMPLATE = (REPO_ROOT / "templates" / "repo-init.yaml").read_text()

CONTEXT_ROW = "context"


def repo_init() -> Plan:
    result = validate(TEMPLATE, templates=FakeTemplateVersionRepository([]))
    assert result.template is not None, result.errors
    return plan_run(
        ResolvedTree(root=result.template),
        fixtures.inputs(),
        git=fixtures.repo_init_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )


def context_row() -> dict[str, Any]:
    return next(row for row in repo_init().rows if row.path == CONTEXT_ROW).with_resolved


# ── what the plan writes ────────────────────────────────────────────────────


def test_a_dispatch_with_no_story_behind_it_carries_no_story_file_contract() -> None:
    """AD-7: the plan decides what a row evaluates, and this row has nothing to evaluate."""
    assert EXPECT_KEY not in context_row()


def test_it_still_carries_everything_a_dispatch_needs() -> None:
    """Dropping the contract must not drop the row: only `expect` goes."""
    resolved = context_row()

    assert resolved["skill"] == "bmad-project-context"
    assert resolved["writes"] == ["AGENTS.md"]
    assert RETRY_KEY in resolved


def test_the_three_keys_that_describe_a_story_are_all_blank_on_it() -> None:
    """The blanks the glob was being built from — the reason the contract cannot exist."""
    resolved = context_row()

    assert resolved["story"] is None
    assert resolved["story_id"] is None
    assert resolved["spec_folder"] is None


# ── what the executor does with the row the plan really wrote ───────────────


def test_the_executor_reports_what_the_dispatch_did_and_globs_nothing() -> None:
    """The whole defect, end to end over the fakes: this raised `path outside the workspace:
    /stories/-*.md` and parked the Run `internal`."""
    world = a_tail_world(with_resolved=context_row(), story=None)

    result = AgentExecutor().execute(world.ctx)

    assert result.status == "done"
    assert result.park is None
    assert result.output_ref == str(LOG_PATH)


def test_it_asks_the_workspace_for_no_story_glob_at_all() -> None:
    """`story_files` answers `None` before a Workspace is even reached."""
    world = a_tail_world(with_resolved=context_row(), story=None)

    AgentExecutor().execute(world.ctx)

    assert world.workspace.globbed == []
