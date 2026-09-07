"""Fresh branch names (`templates/branches.py`): no Run works where another one already did.

The rule this module covers is one sentence — the branch a Template *declares* is not the
branch a Run *creates* — and the reason it is worth its own module is that four things read
the two names differently: `git.worktree` creates the fresh one, `git.push` pushes it,
`pr.link` links it, and `plan_ref`, `read_list` and pre-flight's `held by run` all still ask
the origin about the declared one.

The allocator is driven through a `PlanReader` over `FakeGit`, because "free on the origin"
is a question about the remote and the memoised reader is the only way the planner may ask
it (AD-7).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.application.steps import KIND_META, PUSH_KIND, WORKTREE_KIND
from orchestrator.application.templates.branches import (
    MAX_SUFFIX,
    BranchAllocator,
    fresh_params,
)
from orchestrator.application.templates.model import ParsedTemplate, Step
from orchestrator.application.templates.plan_model import NO_FREE_BRANCH, PlanError
from orchestrator.application.templates.reader import PlanReader
from orchestrator.application.templates.rows import Frame
from tests.unit.fakes.git import FakeGit

BASE = Path("/work/my-project/my-repo/base")
URL = "https://example.test/org/my-repo.git"
SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4"

DECLARED = "chore/bmad-init"
BASE_BRANCH = "main"


def allocator(*held: str) -> BranchAllocator:
    """An allocator over an origin already holding exactly the branches named."""
    refs = {BASE_BRANCH: SHA, **{branch: SHA for branch in held}}
    return BranchAllocator(PlanReader(FakeGit(refs=refs), base=BASE, url=URL))


def frame(**overrides: object) -> Frame:
    template = ParsedTemplate(name="repo-init", version=1, line=1, steps=())
    fields: dict[str, object] = {
        "prefix": "",
        "labels": (),
        "ref": SHA,
        "scope": {},
        "template": template,
    }
    fields.update(overrides)
    return Frame(**fields)  # type: ignore[arg-type]


def worktree_step() -> Step:
    return Step(
        id="checkout",
        line=1,
        uses=WORKTREE_KIND,
        meta=KIND_META[WORKTREE_KIND],
        params=(("base", BASE_BRANCH), ("branch", DECLARED)),
    )


def push_step() -> Step:
    return Step(
        id="push",
        line=1,
        uses=PUSH_KIND,
        meta=KIND_META[PUSH_KIND],
        params=(("branch", DECLARED),),
    )


# --- the ordinal ------------------------------------------------------------------------------


def test_the_first_run_of_a_template_still_gets_an_ordinal() -> None:
    """No bare name is ever created, so a second Run has nothing to collide with."""
    assert allocator().fresh(DECLARED) == "chore/bmad-init-1"


def test_a_name_the_origin_already_holds_is_skipped() -> None:
    fresh = allocator("chore/bmad-init-1", "chore/bmad-init-2").fresh(DECLARED)

    assert fresh == "chore/bmad-init-3"


def test_one_declared_branch_gets_one_name_for_the_whole_plan() -> None:
    """`git.worktree`, `git.push` and `pr.link` all name it; three allocations would be
    three branches."""
    allocate = allocator()

    assert allocate.fresh(DECLARED) == allocate.fresh(DECLARED)


def test_two_declared_branches_never_collide_on_one_name() -> None:
    """`feat/x` and `feat/x-1` in one plan: the second may not be handed the first's name."""
    allocate = allocator()

    assert allocate.fresh("feat/x") == "feat/x-1"
    assert allocate.fresh("feat/x-1") == "feat/x-1-1"


def test_a_template_that_checks_nothing_out_gets_no_name() -> None:
    """`initiative@1`: its worktree is inside the epic frame (AD-7)."""
    assert allocator().fresh(None) is None


def test_a_repository_nobody_is_tidying_is_refused_rather_than_walked_forever() -> None:
    taken = [f"{DECLARED}-{ordinal}" for ordinal in range(1, MAX_SUFFIX + 1)]

    with pytest.raises(PlanError) as raised:
        allocator(*taken).fresh(DECLARED)

    assert raised.value.reason == NO_FREE_BRANCH
    assert raised.value.item == DECLARED


def test_the_allocated_map_is_what_the_plan_carries_for_preflight() -> None:
    allocate = allocator()
    allocate.fresh(DECLARED)

    assert allocate.allocated == {DECLARED: "chore/bmad-init-1"}


# --- where the fresh branch starts --------------------------------------------------------------


def test_a_declared_branch_the_origin_holds_is_where_the_fresh_one_starts() -> None:
    """The plan was read at that branch's head, so the worktree has to hold that tree."""
    assert allocator(DECLARED).start_point(DECLARED, BASE_BRANCH) == DECLARED


def test_a_declared_branch_the_origin_lacks_starts_from_the_template_s_own_base() -> None:
    assert allocator().start_point(DECLARED, BASE_BRANCH) == BASE_BRANCH


def test_a_template_with_no_branch_starts_from_the_base() -> None:
    assert allocator().start_point(None, BASE_BRANCH) == BASE_BRANCH


# --- what a row carries -------------------------------------------------------------------------


def test_the_worktree_row_creates_the_fresh_branch_from_the_declared_one() -> None:
    inner = frame(branch=DECLARED, fresh_branch="chore/bmad-init-2", fresh_from=DECLARED)

    resolved = fresh_params(worktree_step(), inner, {"base": BASE_BRANCH, "branch": DECLARED})

    assert resolved == {"base": DECLARED, "branch": "chore/bmad-init-2"}


def test_a_worktree_row_keeps_its_own_base_when_the_declared_branch_is_new() -> None:
    inner = frame(branch=DECLARED, fresh_branch="chore/bmad-init-1", fresh_from=BASE_BRANCH)

    resolved = fresh_params(worktree_step(), inner, {"base": BASE_BRANCH, "branch": DECLARED})

    assert resolved == {"base": BASE_BRANCH, "branch": "chore/bmad-init-1"}


def test_a_push_row_pushes_the_branch_the_worktree_row_created() -> None:
    inner = frame(branch=DECLARED, fresh_branch="chore/bmad-init-1", fresh_from=BASE_BRANCH)

    resolved = fresh_params(push_step(), inner, {"branch": DECLARED})

    assert resolved == {"branch": "chore/bmad-init-1"}


def test_a_row_naming_some_other_branch_is_left_alone() -> None:
    """Inventing a name for it would push work to a branch nobody planned."""
    inner = frame(branch=DECLARED, fresh_branch="chore/bmad-init-1", fresh_from=BASE_BRANCH)

    resolved = fresh_params(push_step(), inner, {"branch": "release/1.0"})

    assert resolved == {"branch": "release/1.0"}


def test_a_frame_with_no_branch_of_its_own_rewrites_nothing() -> None:
    resolved = fresh_params(push_step(), frame(), {"branch": DECLARED})

    assert resolved == {"branch": DECLARED}
