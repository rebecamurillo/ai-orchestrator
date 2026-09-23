"""`application/steps/git_submodule.py`: the hub Run's member repositories (AD-9, AD-14).

One kind, two forms, told apart by the `with` keys the row carries (spine "Template DSL v1
keys", ratified 2026-09-23):

- **bare, or `{update: true}`** → init + update of the Run worktree's submodules, reporting
  the workdirs it materialised, so the Operator can read off the row which member
  repositories this Run is about to work in.
- **`{workdir, branch, base?}`** → create-or-checkout of that branch inside one submodule,
  reporting the sha its HEAD reached.

The keys of both forms together, and a `workdir` with no `branch`, are a validation error
(`tests/unit/application/templates/test_submodule_kind.py`). This module asserts the
executor's own backstop for the same shape, because a row can reach an executor with a
`with_resolved` no validator saw — `{{…}}` resolution happens at plan time, and a park the
Operator can read is the only honest answer to a row nothing can decide the form of.
"""

from __future__ import annotations

import pytest

from orchestrator.application.steps.context import NO_WORKTREE, StepExecutor
from orchestrator.application.steps.git_submodule import (
    AMBIGUOUS_FORM,
    BASE_KEY,
    BRANCH_KEY,
    INITIALIZED,
    KIND,
    NO_BRANCH,
    NOT_A_SUBMODULE,
    NOTHING_TO_INITIALIZE,
    UPDATE_KEY,
    WORKDIR_KEY,
    GitSubmoduleExecutor,
)
from orchestrator.application.steps.registry import executor_for
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.git import GitError
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import WORKTREE, a_context, a_row

WORKDIR = "repos/member"
OTHER_WORKDIR = "repos/other"
BRANCH = "feat/initiative-7"
MEMBER_BASE = "main"
SHA = "beef0123456789abcdefbeef0123456789abcdef"
PATH = "submodules"


def a_git(*, update: list[object] | None = None, checkout: list[object] | None = None) -> FakeGit:
    """The one shared `Git` fake, with only this kind's two methods scripted (AD-18)."""
    return FakeGit(submodule_update=update, submodule_checkout=checkout)


def a_submodule_row(**with_resolved: object) -> StepRun:
    return a_row(kind=KIND, with_resolved={"timeout_min": 10, **with_resolved}, path=PATH)


def test_the_executor_satisfies_the_protocol_and_is_the_registered_one() -> None:
    assert isinstance(GitSubmoduleExecutor(), StepExecutor)
    assert isinstance(executor_for(KIND), GitSubmoduleExecutor)


# ── the update form ─────────────────────────────────────────────────────────


def test_a_bare_row_updates_the_worktrees_submodules_and_reports_the_workdirs() -> None:
    git = a_git(update=[(WORKDIR, OTHER_WORKDIR)])

    result = GitSubmoduleExecutor().execute(a_context(a_submodule_row(), git=git))

    assert result.status == "done"
    assert result.reason == INITIALIZED.format(paths=f"{WORKDIR}, {OTHER_WORKDIR}")
    assert result.park is None


def test_the_update_runs_in_the_runs_own_worktree() -> None:
    git = a_git(update=[(WORKDIR,)])

    GitSubmoduleExecutor().execute(a_context(a_submodule_row(), git=git))

    assert [str(worktree) for (worktree,) in git.called("submodule_update")] == [WORKTREE]
    assert git.called("submodule_checkout") == []


def test_the_explicit_update_key_is_the_same_form_as_the_bare_one() -> None:
    git = a_git(update=[(WORKDIR,)])

    result = GitSubmoduleExecutor().execute(
        a_context(a_submodule_row(**{UPDATE_KEY: True}), git=git)
    )

    assert result.status == "done"
    assert result.reason == INITIALIZED.format(paths=WORKDIR)


def test_a_worktree_with_no_submodules_is_done_and_says_so() -> None:
    """`()` is the port's "nothing to initialize", and a row that reports it is not a
    failure: a hub Template run against a repository with no members is a Run that does
    nothing here, not a Run that stops."""
    git = a_git(update=[()])

    result = GitSubmoduleExecutor().execute(a_context(a_submodule_row(), git=git))

    assert result.status == "done"
    assert result.reason == NOTHING_TO_INITIALIZE
    assert result.park is None


def test_a_clone_the_credential_could_not_make_parks_misconfigured_with_gits_words() -> None:
    """A private member repository the token cannot reach is a configuration fact for the
    Operator, and git's own message — already redacted by the adapter — is what says which."""
    failure = GitError(
        command="git submodule update --init", exit_code=128, output="fatal: could not read"
    )
    git = a_git(update=[failure])

    result = GitSubmoduleExecutor().execute(a_context(a_submodule_row(), git=git))

    assert result.status == "error"
    assert result.output_ref == "fatal: could not read"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.path == PATH


# ── the checkout form ───────────────────────────────────────────────────────


def test_a_checkout_row_is_done_with_the_sha_the_submodules_head_reached() -> None:
    git = a_git(checkout=[SHA])

    result = GitSubmoduleExecutor().execute(
        a_context(a_submodule_row(**{WORKDIR_KEY: WORKDIR, BRANCH_KEY: BRANCH}), git=git)
    )

    assert result.status == "done"
    assert result.output_ref == SHA
    assert result.park is None


def test_the_checkout_passes_the_declared_workdir_branch_and_base_through() -> None:
    git = a_git(checkout=[SHA])

    GitSubmoduleExecutor().execute(
        a_context(
            a_submodule_row(**{WORKDIR_KEY: WORKDIR, BRANCH_KEY: BRANCH, BASE_KEY: MEMBER_BASE}),
            git=git,
        )
    )

    assert [
        (str(worktree), workdir, branch, base)
        for worktree, workdir, branch, base in git.called("submodule_checkout")
    ] == [(WORKTREE, WORKDIR, BRANCH, MEMBER_BASE)]
    assert git.called("submodule_update") == []


def test_a_checkout_with_no_base_declares_none_rather_than_an_empty_string() -> None:
    """AD-14 gives "no base declared" and "a base the member does not hold" one answer — the
    submodule's current HEAD — and `None` is how the port is told which case this is."""
    git = a_git(checkout=[SHA])

    GitSubmoduleExecutor().execute(
        a_context(a_submodule_row(**{WORKDIR_KEY: WORKDIR, BRANCH_KEY: BRANCH}), git=git)
    )

    assert git.called("submodule_checkout")[0][3] is None


def test_an_empty_base_is_read_as_no_base_at_all() -> None:
    """A `{{epic.base}}` an entry omitted resolves empty (AD-7), and an empty ref name is
    not a start point — it is the absence the fallback already has an answer for."""
    git = a_git(checkout=[SHA])

    GitSubmoduleExecutor().execute(
        a_context(
            a_submodule_row(**{WORKDIR_KEY: WORKDIR, BRANCH_KEY: BRANCH, BASE_KEY: "  "}),
            git=git,
        )
    )

    assert git.called("submodule_checkout")[0][3] is None


def test_a_workdir_that_is_not_an_initialized_submodule_parks_the_spines_sentence() -> None:
    git = a_git(checkout=[None])

    result = GitSubmoduleExecutor().execute(
        a_context(a_submodule_row(**{WORKDIR_KEY: WORKDIR, BRANCH_KEY: BRANCH}), git=git)
    )

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == f"workdir {WORKDIR} is not an initialized submodule"
    assert result.reason == NOT_A_SUBMODULE.format(path=WORKDIR)


def test_a_failed_checkout_parks_misconfigured_with_gits_output_beside_it() -> None:
    failure = GitError(command="git fetch origin", exit_code=128, output="fatal: no access")
    git = a_git(checkout=[failure])

    result = GitSubmoduleExecutor().execute(
        a_context(a_submodule_row(**{WORKDIR_KEY: WORKDIR, BRANCH_KEY: BRANCH}), git=git)
    )

    assert result.status == "error"
    assert result.output_ref == "fatal: no access"
    assert result.park is not None
    assert result.park.kind == "misconfigured"


# ── the two forms are exclusive ─────────────────────────────────────────────


def test_the_keys_of_both_forms_together_park_rather_than_picking_one() -> None:
    """The validator rejects this shape; the executor is the backstop, because picking a
    form would be exactly the silent fall back AD-9 forbids."""
    git = a_git()

    result = GitSubmoduleExecutor().execute(
        a_context(
            a_submodule_row(**{UPDATE_KEY: True, WORKDIR_KEY: WORKDIR, BRANCH_KEY: BRANCH}),
            git=git,
        )
    )

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == AMBIGUOUS_FORM
    assert git.calls == []


def test_a_workdir_with_no_branch_parks_rather_than_updating_everything() -> None:
    git = a_git()

    result = GitSubmoduleExecutor().execute(
        a_context(a_submodule_row(**{WORKDIR_KEY: WORKDIR}), git=git)
    )

    assert result.status == "error"
    assert result.park is not None
    assert result.park.reason == NO_BRANCH
    assert git.calls == []


def test_a_branch_with_no_workdir_parks_rather_than_guessing_a_submodule() -> None:
    git = a_git()

    result = GitSubmoduleExecutor().execute(
        a_context(a_submodule_row(**{BRANCH_KEY: BRANCH}), git=git)
    )

    assert result.status == "error"
    assert result.park is not None
    assert result.park.reason == AMBIGUOUS_FORM
    assert git.calls == []


# ── the wiring the kind needs ───────────────────────────────────────────────


def test_a_row_reached_before_any_worktree_exists_refuses() -> None:
    with pytest.raises(RuntimeError, match="no worktree"):
        GitSubmoduleExecutor().execute(a_context(a_submodule_row(), cwd=None))
    assert NO_WORKTREE.format(path=PATH).startswith("no worktree")
