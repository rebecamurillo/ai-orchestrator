"""An `epic@1` Run on a branch the remote does not hold yet, planned and then checked (FR-8).

This is the shape every readiness Run has and every Epic 6 scenario starts from: the
Template names a working branch, nobody has pushed it, so `plan_ref` falls back to the base
branch and every list file is read off the base's own commit.

`PlanReader.record`'s own docstring states the contract — "`None` means the file was read
straight off the frame's own ref rather than a branch fallback — which is exactly what a
Template naming no branch, **or naming one the remote does not hold yet**, resolves to" —
and `plan.check` reads it that way: `list_branches.get(path) or base_branch`.

Recording the working branch regardless made `plan.check` ask `ls_remote(url, branch)` for a
branch that is not there, read `None` for the current content, compare it against the text
the plan was built from, and park `plan_stale` on row 1 of the first Run of every new
branch. The two halves are proven together — what the planner records, and that the row
built from it comes back `done` — because either alone would let the other drift.

`tests/unit/test_plan_check_row_with_resolved.py` covers the branch the remote *does* hold,
and nothing here changes it: a Template working on a pushed branch still records that branch,
because that is the branch a fresh copy of its list file would come from.
"""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext, StepPorts
from orchestrator.application.steps.plan_check import (
    BASE_BRANCH_KEY,
    LIST_BRANCHES_KEY,
    PLAN_REFS_KEY,
    PlanCheckExecutor,
)
from orchestrator.application.templates.plan import plan_run
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import PlannedRow
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit

STORIES_PATH = f"{fixtures.SPEC_FOLDER}/stories.yaml"
WORK_DIR = "/work"


def unpushed_branch_git() -> FakeGit:
    """A remote holding the base branch and nothing else — `epic@1`'s first Run.

    The same repository the readiness fixture is: one `main`, and a working branch the Run
    is about to create. `epic_git()` in `plan_fixtures` is the opposite case and stays it.
    """
    return FakeGit(
        refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA},
        files={(fixtures.BASE_SHA, STORIES_PATH): fixtures.EPIC_STORIES},
        listings={},
    )


def a_context(row: PlannedRow, git: FakeGit) -> StepContext:
    """The `plan.check` row as the walker hands it to its executor (AD-9)."""
    stored = StepRun(
        id=new_id(),
        run_id=new_id(),
        seq=row.seq,
        path=row.path,
        label=row.label,
        kind=row.kind,
        gate=row.gate,
        status="running",
        with_resolved=row.with_resolved,
    )
    return StepContext(
        row=stored,
        with_resolved=stored.with_resolved,
        cwd=None,
        frame_start_sha=None,
        previous_attempt=None,
        attempt=Attempt(
            id=new_id(), run_id=stored.run_id, step_run_id=stored.id, n=1, status="running"
        ),
        resume_signal=None,
        ports=StepPorts(git=git, clock=FakeClock(EPOCH), work_dir=WORK_DIR),
    )


def a_plan(git: FakeGit) -> tuple[PlannedRow, dict[str, object]]:
    """`epic@1` planned against one scripted remote: row 1, and what it carries."""
    plan = plan_run(
        fixtures.tree("epic"),
        fixtures.epic_inputs(),
        git=git,
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )
    return plan.rows[0], dict(plan.rows[0].with_resolved)


# ── what the planner records ────────────────────────────────────────────────


def test_the_whole_plan_is_read_at_the_base_when_the_working_branch_is_not_there() -> None:
    """`plan_ref`'s own fallback — the premise the recording rule below is about."""
    plan = plan_run(
        fixtures.tree("epic"),
        fixtures.epic_inputs(),
        git=unpushed_branch_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )

    assert plan.plan_ref == fixtures.BASE_SHA
    assert plan.plan_refs == {STORIES_PATH: fixtures.BASE_SHA}


def test_a_list_file_read_off_the_base_records_no_branch() -> None:
    """The branch the Template names is not where the file came from, so it is not recorded."""
    _, resolved = a_plan(unpushed_branch_git())

    assert resolved[LIST_BRANCHES_KEY] == {STORIES_PATH: None}
    assert resolved[BASE_BRANCH_KEY] == fixtures.BASE_BRANCH


def test_a_list_file_read_off_a_branch_the_remote_holds_still_records_that_branch() -> None:
    """The Initiative case, unchanged: a pushed branch is where a fresh copy would come from."""
    _, resolved = a_plan(fixtures.epic_git())

    assert resolved[PLAN_REFS_KEY] == {STORIES_PATH: fixtures.WORK_SHA}
    assert resolved[LIST_BRANCHES_KEY] == {STORIES_PATH: fixtures.EPIC_BRANCH}


# ── and what the row built from it then does ────────────────────────────────


def test_row_one_of_a_fresh_branch_run_is_done_rather_than_plan_stale() -> None:
    """End to end over the two modules: nothing drifted, so nothing parks."""
    git = unpushed_branch_git()
    row, _ = a_plan(git)

    result = PlanCheckExecutor().execute(a_context(row, unpushed_branch_git()))

    assert result.status == "done"
    assert result.park is None


def test_the_check_asks_the_base_branch_for_the_current_copy() -> None:
    """The one `ls_remote` the row makes names the branch the file was read from."""
    git = unpushed_branch_git()
    row, _ = a_plan(git)
    checking = unpushed_branch_git()

    PlanCheckExecutor().execute(a_context(row, checking))

    assert [ref for _url, ref in checking.called("ls_remote")] == [fixtures.BASE_BRANCH]


def test_a_fresh_branch_run_whose_list_file_really_changed_still_parks() -> None:
    """The check is not disabled by the fallback: drift on the base branch is still drift."""
    row, _ = a_plan(unpushed_branch_git())
    moved = FakeGit(
        refs={fixtures.BASE_BRANCH: fixtures.WORK_SHA},
        files={
            (fixtures.BASE_SHA, STORIES_PATH): fixtures.EPIC_STORIES,
            (fixtures.WORK_SHA, STORIES_PATH): fixtures.four_stories("9"),
        },
        listings={},
    )

    result = PlanCheckExecutor().execute(a_context(row, moved))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "plan_stale"
