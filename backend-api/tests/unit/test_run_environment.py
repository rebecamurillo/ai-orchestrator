"""`RunEnvironment` and the `ProtectedPaths` port: what a git executor is handed (AD-9, AD-17).

`StepContext`'s field list is closed by AD-9, so the Run's own facts travel inside
`StepPorts` as a frozen value the walker resolved. What is asserted here is that it *is* one
— frozen, and computing AD-14's two paths the same way `use_cases/clone_check.py` does — and
that the frozen-anchor seam is a structural port, so Epic 5 implements it without changing a
line of `git.commit`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import FrozenInstanceError

import pytest

from orchestrator.application.steps.context import (
    NO_ENVIRONMENT,
    NO_RUNNER,
    NO_WORKSPACE,
    NO_WORKTREE,
    RunEnvironment,
    StepPorts,
    require_cwd,
    require_env,
    require_process,
    require_workspace,
)
from orchestrator.domain.ports.protected_paths import ProtectedPaths
from tests.unit.step_fixtures import (
    BASE_DIR,
    BRANCH,
    WORK_DIR,
    WORKTREE,
    a_context,
    a_row,
    a_worktree,
    an_environment,
    without,
)


class NoHits:
    """The rule Epic 5 lands, as a structural implementation of the port today."""

    def check(self, *, changed: Sequence[str], accepted: Sequence[str]) -> tuple[str, ...]:
        return ()


def test_the_environment_is_frozen_so_no_executor_can_edit_what_it_was_handed() -> None:
    env = an_environment()

    with pytest.raises(FrozenInstanceError):
        env.install_command = "rm -rf /"  # type: ignore[misc]


def test_the_base_clone_path_is_ad_14s_one_layout() -> None:
    assert str(an_environment().base_dir(WORK_DIR)) == BASE_DIR


def test_a_slash_in_a_branch_name_becomes_a_directory_level() -> None:
    """AD-14 says so, and `Path` does it without a rule of its own."""
    assert str(an_environment().worktree_dir(WORK_DIR, BRANCH)) == WORKTREE


def test_the_run_finds_the_worktree_it_is_standing_in_by_its_path() -> None:
    env = an_environment(worktrees=(a_worktree(),))

    found = env.worktree_at(WORKTREE)

    assert found is not None
    assert found.branch == BRANCH


def test_a_path_no_entry_records_is_not_a_worktree_this_run_made() -> None:
    assert an_environment(worktrees=(a_worktree(),)).worktree_at("/work/elsewhere") is None
    assert an_environment().worktree_at(None) is None


# ── the wiring helpers ──────────────────────────────────────────────────────


def test_the_helpers_hand_back_what_the_composition_root_wired() -> None:
    context = a_context(a_row(kind="git.sync", with_resolved={}))

    assert isinstance(require_env(context), RunEnvironment)
    assert require_workspace(context, context.cwd) is not None
    assert str(require_cwd(context)) == WORKTREE


def test_each_unset_port_refuses_by_name_rather_than_failing_later() -> None:
    context = a_context(a_row(kind="git.sync", with_resolved={}))

    with pytest.raises(RuntimeError, match=NO_ENVIRONMENT):
        require_env(without(context, run_env=None))
    with pytest.raises(RuntimeError, match=NO_RUNNER):
        require_process(without(context, process=None))
    with pytest.raises(RuntimeError, match=NO_WORKSPACE):
        require_workspace(without(context, workspace=None), context.cwd)


def test_a_row_with_no_worktree_yet_is_named_in_its_own_refusal() -> None:
    row = a_row(kind="git.sync", with_resolved={}, path="stories[0].sync")
    context = a_context(row, cwd=None)

    with pytest.raises(RuntimeError, match=NO_WORKTREE.format(path="stories\\[0\\].sync")):
        require_cwd(context)


# ── the seam AD-17 fills in Epic 5 ──────────────────────────────────────────


def test_the_protected_path_seam_is_a_structural_port() -> None:
    assert isinstance(NoHits(), ProtectedPaths)
    assert NoHits().check(changed=("AGENTS.md",), accepted=()) == ()


def test_epic_4_wires_no_rule_at_all() -> None:
    """`git.commit` reads that as no hits; the port's own docstring says why."""
    assert StepPorts(git=None, clock=None, work_dir=WORK_DIR).protected_paths is None  # type: ignore[arg-type]
