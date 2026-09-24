"""`infrastructure/git/submodules.py`, against real `git` (AD-14, amended 2026-09-23).

The executor is proven over `FakeGit`; what only a real process settles is how `git
submodule` behaves **in a linked worktree** — which is the only kind of tree this system
ever has one in. Every fixture here therefore builds AD-14's own layout: a bare hub origin
carrying a `repos/member` submodule, a blobless `--no-checkout` base clone of it at
`work/{project}/{repo}/base`, and the worktree added from that base at `wt/{branch}`.

Four facts this module is the only place to establish, all of them empirical (story H1,
2026-09-23):

- **A linked worktree's submodules are its own.** git puts a submodule's git directory at
  `base/.git/worktrees/{worktree}/modules/{name}`, not at the shared `base/.git/modules/`,
  so two worktrees of one base clone each initialize their own checkout of the same
  submodule and neither can move the other's HEAD. The hub workflow depends on that: a
  submodule is "a working folder inside a worktree, never a second workspace" (AD-14).
- **`submodule.{name}.url` does land in the base clone's shared config**, which worktrees
  share, and a second `init` does **not** overwrite one already recorded. It is the same
  URL for every worktree of one repository, so this is idempotent rather than a race.
- **The credential path reaches the child processes.** `git submodule` does its cloning and
  fetching in child processes, which inherit the environment `SubprocessGit` built — so
  `GIT_ASKPASS` covers a private member repository without the adapter passing anything
  extra (AD-5). Asserted by observing the environment a submodule child process actually
  runs with.
- **`file://` submodules are refused by git unless the transport is allowed** (the
  CVE-2022-39253 guard, git ≥ 2.38). Real member repositories are `https`, so the adapter
  must never relax that; `allow_file_transport` below does it for the fixture only, by
  writing a global config into the private `HOME` the adapter already gives every command —
  which is also a second proof that the child clones read the adapter's environment.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator.infrastructure.git.submodules import UNINITIALIZED
from orchestrator.infrastructure.git.subprocess_git import SubprocessGit

TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"
BASE_BRANCH = "main"
INTEGRATION = "integration"
#: A hub branch cut before the gitlink existed — a worktree with nothing to initialize.
NO_SUBMODULES = "before-the-members"
#: A second worktree of the same base clone, to settle who owns a submodule checkout.
OTHER = "other"
MEMBER_BASE = "main"
MEMBER_HELD = "feat/held-by-the-member"
WORKDIR = "repos/member"
SEED_FILE = "README.md"
MEMBER_FILE = "member.txt"
HELD_FILE = "held.txt"
NEW_BRANCH = "feat/initiative-7"


@pytest.fixture(autouse=True)
def git_binary() -> str:
    """`git` is a requirement of this suite, not a condition on running it (AD-18)."""
    found = shutil.which("git")
    if found is None:
        pytest.fail("git is not on PATH: this module drives the real adapter, so install it.")
    return found


def run_git(*arguments: str, cwd: Path) -> str:
    """Set up a fixture repository. The adapter is what is under test, not this."""
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "e2e",
        "GIT_AUTHOR_EMAIL": "e2e@example.invalid",
        "GIT_COMMITTER_NAME": "e2e",
        "GIT_COMMITTER_EMAIL": "e2e@example.invalid",
        # the fixture's own `submodule add`, for the reason `allow_file_transport` exists
        "GIT_ALLOW_PROTOCOL": "file",
    }
    return subprocess.run(  # fixed argv, no shell
        ["git", *arguments], cwd=cwd, env=environment, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def member_origin(tmp_path: Path) -> Path:
    """A bare member repository holding `main` and one branch of its own."""
    bare = tmp_path / "member.git"
    run_git("init", "--quiet", "--bare", str(bare), cwd=tmp_path)
    seed = tmp_path / "member-seed"
    seed.mkdir()
    run_git("init", "--quiet", f"--initial-branch={MEMBER_BASE}", ".", cwd=seed)
    (seed / MEMBER_FILE).write_text("member\n")
    run_git("add", "--all", cwd=seed)
    run_git("commit", "--quiet", "--message", "member seed", cwd=seed)
    run_git("checkout", "--quiet", "-b", MEMBER_HELD, cwd=seed)
    (seed / HELD_FILE).write_text("only on the member's own branch\n")
    run_git("add", "--all", cwd=seed)
    run_git("commit", "--quiet", "--message", "member branch work", cwd=seed)
    run_git(
        "push",
        "--quiet",
        f"file://{bare}",
        f"{MEMBER_BASE}:{MEMBER_BASE}",
        f"{MEMBER_HELD}:{MEMBER_HELD}",
        cwd=seed,
    )
    run_git("symbolic-ref", "HEAD", f"refs/heads/{MEMBER_BASE}", cwd=bare)
    return bare


@pytest.fixture
def hub_origin(tmp_path: Path, member_origin: Path) -> Path:
    """A bare hub repository whose `repos/member` gitlink points at the member origin."""
    bare = tmp_path / "hub.git"
    run_git("init", "--quiet", "--bare", str(bare), cwd=tmp_path)
    seed = tmp_path / "hub-seed"
    seed.mkdir()
    run_git("init", "--quiet", f"--initial-branch={BASE_BRANCH}", ".", cwd=seed)
    (seed / SEED_FILE).write_text("the hub\n")
    run_git("add", "--all", cwd=seed)
    run_git("commit", "--quiet", "--message", "hub seed", cwd=seed)
    run_git("branch", NO_SUBMODULES, cwd=seed)
    run_git("submodule", "--quiet", "add", f"file://{member_origin}", WORKDIR, cwd=seed)
    run_git("commit", "--quiet", "--message", "add the member submodule", cwd=seed)
    run_git("branch", INTEGRATION, cwd=seed)
    run_git(
        "push",
        "--quiet",
        f"file://{bare}",
        f"{BASE_BRANCH}:{BASE_BRANCH}",
        f"{INTEGRATION}:{INTEGRATION}",
        f"{NO_SUBMODULES}:{NO_SUBMODULES}",
        cwd=seed,
    )
    run_git("symbolic-ref", "HEAD", f"refs/heads/{BASE_BRANCH}", cwd=bare)
    return bare


def allow_file_transport(git: SubprocessGit) -> None:
    """Let this fixture's `file://` member origin be cloned as a submodule.

    git ≥ 2.38 refuses the `file` transport for a clone a *submodule* started
    (CVE-2022-39253) unless `protocol.file.allow` says otherwise, and a repository-local
    setting does not reach it: the clone is a child process with a repository of its own.
    What does reach it is the adapter's own environment, so the fixture writes a global
    config into the private empty `HOME` that `command_environment` gives every command.

    Two things follow, and both are deliberate. Production is untouched — a real member
    repository is `https`, and an adapter that passed `protocol.file.allow=always` itself
    would be re-opening the vulnerability for every Run. And the fact that this works at all
    is the second proof of `test_a_submodule_child_process_runs_with_the_adapters_own_env`:
    the child clone read a config file it could only have found through `HOME`.
    """
    home = Path(git._home)
    (home / ".gitconfig").write_text('[protocol "file"]\n\tallow = always\n')


@pytest.fixture
def git() -> SubprocessGit:
    adapter = SubprocessGit(TOKEN)
    allow_file_transport(adapter)
    return adapter


@pytest.fixture
def base(git: SubprocessGit, hub_origin: Path, tmp_path: Path) -> Path:
    destination = tmp_path / "work" / "acme" / "hub" / "base"
    git.clone_base(f"file://{hub_origin}", destination)
    git.fetch_base(destination, INTEGRATION)
    return destination


@pytest.fixture
def worktree(git: SubprocessGit, base: Path, tmp_path: Path) -> Path:
    """The initiative branch, attached by its exact name — a hub Run's own worktree."""
    path = tmp_path / "work" / "acme" / "hub" / "wt" / INTEGRATION
    git.worktree_add(base, path, INTEGRATION, None)
    return path


@pytest.fixture
def initialized(git: SubprocessGit, worktree: Path) -> Path:
    """The same worktree with its submodules materialised — the checkout form's precondition."""
    git.submodule_update(worktree)
    return worktree


def head_of(submodule: Path) -> str:
    return run_git("rev-parse", "HEAD", cwd=submodule).strip()


def branch_of(submodule: Path) -> str:
    return run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=submodule).strip()


# ── submodule_update ────────────────────────────────────────────────────────


def test_update_materialises_the_submodule_and_answers_its_repository_relative_path(
    git: SubprocessGit, worktree: Path
) -> None:
    initialized = git.submodule_update(worktree)

    assert initialized == (WORKDIR,)
    assert (worktree / WORKDIR / MEMBER_FILE).read_text() == "member\n"


def test_an_uninitialized_submodule_is_an_empty_folder_before_the_row_runs(
    worktree: Path,
) -> None:
    """What a `git.worktree` row alone leaves: a gitlink, and nothing to run a step in."""
    assert (worktree / WORKDIR).is_dir()
    assert list((worktree / WORKDIR).iterdir()) == []


def test_update_is_idempotent_and_answers_the_same_paths_the_second_time(
    git: SubprocessGit, worktree: Path
) -> None:
    """AD-13's `retry` re-runs the row whole, so a second update is the ordinary case."""
    first = git.submodule_update(worktree)
    before = head_of(worktree / WORKDIR)

    assert git.submodule_update(worktree) == first
    assert head_of(worktree / WORKDIR) == before


def test_a_worktree_with_no_submodules_answers_nothing_rather_than_failing(
    git: SubprocessGit, base: Path, tmp_path: Path
) -> None:
    """A hub branch cut before the gitlink existed: nothing to initialize is `()`, not a
    failure — and `repo-init@1` runs on exactly such a tree."""
    path = tmp_path / "work" / "acme" / "hub" / "wt" / NO_SUBMODULES
    git.worktree_add(base, path, NO_SUBMODULES, None)

    assert git.submodule_update(path) == ()


def test_each_linked_worktree_gets_its_own_submodule_checkout(
    git: SubprocessGit, base: Path, initialized: Path, tmp_path: Path
) -> None:
    """The load-bearing finding (H1, 2026-09-23): git stores a linked worktree's submodule
    under `base/.git/worktrees/{worktree}/modules/`, never under the shared
    `base/.git/modules/` — so two Runs on two branches of one hub repository each get their
    own member checkout and neither can move the other's HEAD. The directory name is what
    git keys that by, which under AD-14's `wt/{branch}` layout is the branch's last segment."""
    other = tmp_path / "work" / "acme" / "hub" / "wt" / OTHER
    git.worktree_add(base, other, OTHER, f"origin/{INTEGRATION}")

    assert git.submodule_update(other) == (WORKDIR,)

    first = (initialized / WORKDIR / ".git").read_text()
    second = (other / WORKDIR / ".git").read_text()
    assert first != second
    assert f"worktrees/{INTEGRATION}/modules" in first
    assert f"worktrees/{OTHER}/modules" in second
    assert not (base / ".git" / "modules").exists()


def test_the_submodule_url_is_recorded_once_in_the_config_the_worktrees_share(
    git: SubprocessGit, base: Path, initialized: Path
) -> None:
    """A worktree shares the base clone's config, so `init` writes the URL there. It is the
    same URL for every worktree of one repository, and a second `init` leaves it alone —
    which is what makes the shared config idempotent rather than a race."""
    recorded = run_git("config", f"submodule.{WORKDIR}.url", cwd=base).strip()

    git.submodule_update(initialized)

    assert run_git("config", f"submodule.{WORKDIR}.url", cwd=base).strip() == recorded


def test_a_submodule_child_process_runs_with_the_adapters_own_environment(
    git: SubprocessGit, initialized: Path
) -> None:
    """AD-5 reaching the clones: `git submodule` fetches and clones in child processes, and
    the environment `SubprocessGit` built is what they inherit — so `GIT_ASKPASS` covers a
    private member repository with nothing extra passed. `foreach` is the observable form of
    the same inheritance the clone relies on; the adapter itself runs no shell."""
    seen = git._run("-C", str(initialized), "submodule", "foreach", "--quiet", "echo $GIT_ASKPASS")

    assert seen.strip() == str(git._askpass)


# ── submodule_checkout ──────────────────────────────────────────────────────


def test_a_branch_the_members_remote_holds_is_cut_from_it_and_tracks_it(
    git: SubprocessGit, initialized: Path
) -> None:
    sha = git.submodule_checkout(initialized, WORKDIR, MEMBER_HELD)

    submodule = initialized / WORKDIR
    assert sha == head_of(submodule)
    assert branch_of(submodule) == MEMBER_HELD
    assert (submodule / HELD_FILE).exists()
    assert run_git("rev-parse", "--abbrev-ref", "@{upstream}", cwd=submodule).strip() == (
        f"origin/{MEMBER_HELD}"
    )


def test_a_branch_neither_side_holds_is_cut_from_the_declared_base(
    git: SubprocessGit, initialized: Path
) -> None:
    """The hub workflow's ordinary case: one initiative branch, created in each member
    repository from that repository's own base branch."""
    sha = git.submodule_checkout(initialized, WORKDIR, NEW_BRANCH, MEMBER_BASE)

    submodule = initialized / WORKDIR
    assert branch_of(submodule) == NEW_BRANCH
    assert sha == run_git("rev-parse", f"origin/{MEMBER_BASE}", cwd=submodule).strip()
    assert not (submodule / HELD_FILE).exists()


def test_a_base_the_members_remote_does_not_hold_falls_back_to_the_current_head(
    git: SubprocessGit, initialized: Path
) -> None:
    """AD-14: "from the submodule's current HEAD otherwise". A hub whose members do not all
    share one base-branch name must not fail the row over a name one of them lacks."""
    before = head_of(initialized / WORKDIR)

    sha = git.submodule_checkout(initialized, WORKDIR, NEW_BRANCH, "no-such-base")

    assert sha == before
    assert branch_of(initialized / WORKDIR) == NEW_BRANCH


def test_a_branch_with_no_base_at_all_is_cut_from_the_current_head(
    git: SubprocessGit, initialized: Path
) -> None:
    before = head_of(initialized / WORKDIR)

    assert git.submodule_checkout(initialized, WORKDIR, NEW_BRANCH) == before


def test_the_upstream_is_configured_for_a_branch_the_remote_does_not_hold_yet(
    git: SubprocessGit, initialized: Path
) -> None:
    """ "Upstream set" without the remote ref existing: `branch --set-upstream-to` cannot be
    used, because there is nothing to point at until the first push creates it (H2)."""
    git.submodule_checkout(initialized, WORKDIR, NEW_BRANCH, MEMBER_BASE)

    submodule = initialized / WORKDIR
    assert run_git("config", f"branch.{NEW_BRANCH}.remote", cwd=submodule).strip() == "origin"
    assert run_git("config", f"branch.{NEW_BRANCH}.merge", cwd=submodule).strip() == (
        f"refs/heads/{NEW_BRANCH}"
    )


def test_a_second_checkout_of_the_same_branch_keeps_the_work_the_first_one_left(
    git: SubprocessGit, initialized: Path
) -> None:
    """Idempotent means "not reset": an epic's later rows commit inside the submodule, and a
    re-run of the checkout row must not throw that away."""
    git.submodule_checkout(initialized, WORKDIR, NEW_BRANCH, MEMBER_BASE)
    submodule = initialized / WORKDIR
    (submodule / "work.txt").write_text("what the agent wrote\n")
    run_git("add", "--all", cwd=submodule)
    run_git("commit", "--quiet", "--message", "agent work", cwd=submodule)
    committed = head_of(submodule)

    assert git.submodule_checkout(initialized, WORKDIR, NEW_BRANCH, MEMBER_BASE) == committed
    assert (submodule / "work.txt").exists()


def test_a_checkout_fast_forwards_a_branch_the_member_moved_behind_this_runs_back(
    git: SubprocessGit, initialized: Path, member_origin: Path, tmp_path: Path
) -> None:
    git.submodule_checkout(initialized, WORKDIR, MEMBER_HELD)
    theirs = tmp_path / "theirs"
    run_git(
        "clone",
        "--quiet",
        f"file://{member_origin}",
        "--branch",
        MEMBER_HELD,
        str(theirs),
        cwd=tmp_path,
    )
    (theirs / "later.txt").write_text("landed while the run was elsewhere\n")
    run_git("add", "--all", cwd=theirs)
    run_git("commit", "--quiet", "--message", "later work", cwd=theirs)
    run_git("push", "--quiet", "origin", MEMBER_HELD, cwd=theirs)

    sha = git.submodule_checkout(initialized, WORKDIR, MEMBER_HELD)

    assert (initialized / WORKDIR / "later.txt").exists()
    assert sha == head_of(initialized / WORKDIR)


def test_a_local_branch_that_cannot_fast_forward_is_left_where_it_is(
    git: SubprocessGit, initialized: Path, member_origin: Path, tmp_path: Path
) -> None:
    """ "ff if possible, no error": a diverged branch is a fact for a later row to park on,
    not a reason for the checkout row to refuse."""
    git.submodule_checkout(initialized, WORKDIR, MEMBER_HELD)
    submodule = initialized / WORKDIR
    (submodule / "ours.txt").write_text("this run's work\n")
    run_git("add", "--all", cwd=submodule)
    run_git("commit", "--quiet", "--message", "our work", cwd=submodule)
    ours = head_of(submodule)
    theirs = tmp_path / "theirs"
    run_git(
        "clone",
        "--quiet",
        f"file://{member_origin}",
        "--branch",
        MEMBER_HELD,
        str(theirs),
        cwd=tmp_path,
    )
    (theirs / "theirs.txt").write_text("someone else's work\n")
    run_git("add", "--all", cwd=theirs)
    run_git("commit", "--quiet", "--message", "their work", cwd=theirs)
    run_git("push", "--quiet", "origin", MEMBER_HELD, cwd=theirs)

    assert git.submodule_checkout(initialized, WORKDIR, MEMBER_HELD) == ours


# ── a workdir that is not an initialized submodule ──────────────────────────


def test_a_path_that_is_not_a_submodule_at_all_answers_none(
    git: SubprocessGit, initialized: Path
) -> None:
    assert git.submodule_checkout(initialized, SEED_FILE, NEW_BRANCH) is None


def test_a_path_the_worktree_does_not_hold_answers_none(
    git: SubprocessGit, initialized: Path
) -> None:
    assert git.submodule_checkout(initialized, "repos/absent", NEW_BRANCH) is None


def test_a_submodule_that_was_never_initialized_answers_none_and_writes_nothing(
    git: SubprocessGit, worktree: Path
) -> None:
    """The same answer as "not a submodule", because it is the same stop for the Operator:
    AD-9's `workdir {path} is not an initialized submodule`.

    Also what `UNINITIALIZED` is: git reports the gitlink with that flag in column 1, which
    is the fact the adapter reads rather than guessing from an empty folder."""
    assert run_git("submodule", "status", "--", WORKDIR, cwd=worktree)[0] == UNINITIALIZED

    assert git.submodule_checkout(worktree, WORKDIR, NEW_BRANCH) is None
    assert list((worktree / WORKDIR).iterdir()) == []


# ── submodule_default_branch (H2) ────────────────────────────────────────────


def test_the_default_branch_is_the_submodules_own_remote_head(
    git: SubprocessGit, initialized: Path
) -> None:
    """AD-14 (ratified 2026-09-23): a `workdir` push's refusal reads the SUBMODULE's default
    branch, never the Run Repository's — `member_origin`'s own `main`, not `hub_origin`'s."""
    assert git.submodule_default_branch(initialized, WORKDIR) == MEMBER_BASE


def test_a_path_that_is_not_a_submodule_answers_none_for_the_default_branch(
    git: SubprocessGit, initialized: Path
) -> None:
    assert git.submodule_default_branch(initialized, SEED_FILE) is None


def test_an_uninitialized_submodule_answers_none_for_the_default_branch(
    git: SubprocessGit, worktree: Path
) -> None:
    assert git.submodule_default_branch(worktree, WORKDIR) is None


# ── commit and push with `workdir` (H2, spine AD-9/AD-14 amendment) ─────────


def test_a_workdir_commit_stages_and_commits_inside_the_submodule(
    git: SubprocessGit, initialized: Path
) -> None:
    git.submodule_checkout(initialized, WORKDIR, NEW_BRANCH, MEMBER_BASE)
    submodule = initialized / WORKDIR
    (submodule / "work.txt").write_text("agent work\n")

    sha = git.commit(initialized, "story: workdir commit (orchestrator)", workdir=WORKDIR)

    assert sha == head_of(submodule)
    assert (
        run_git("log", "-1", "--format=%s", cwd=submodule).strip()
        == "story: workdir commit (orchestrator)"
    )
    assert "orchestrator" in run_git("log", "-1", "--format=%an <%ae>", cwd=submodule)


def test_a_workdir_commit_with_nothing_changed_answers_the_existing_head(
    git: SubprocessGit, initialized: Path
) -> None:
    git.submodule_checkout(initialized, WORKDIR, NEW_BRANCH, MEMBER_BASE)
    submodule = initialized / WORKDIR
    before = head_of(submodule)

    sha = git.commit(initialized, "no-op", workdir=WORKDIR)

    assert sha == before
    assert head_of(submodule) == before


def test_a_workdir_commit_to_a_path_that_is_not_a_submodule_answers_none(
    git: SubprocessGit, initialized: Path
) -> None:
    assert git.commit(initialized, "message", workdir=SEED_FILE) is None


def test_a_workdir_push_lands_the_branch_on_the_members_own_origin(
    git: SubprocessGit, initialized: Path, member_origin: Path
) -> None:
    git.submodule_checkout(initialized, WORKDIR, NEW_BRANCH, MEMBER_BASE)
    submodule = initialized / WORKDIR
    (submodule / "work.txt").write_text("agent work\n")
    git.commit(initialized, "story: workdir commit (orchestrator)", workdir=WORKDIR)

    output = git.push(initialized, NEW_BRANCH, True, workdir=WORKDIR)

    assert output is not None
    assert NEW_BRANCH in run_git("branch", "--list", NEW_BRANCH, cwd=member_origin)


def test_a_workdir_push_to_a_path_that_is_not_a_submodule_answers_none(
    git: SubprocessGit, initialized: Path
) -> None:
    assert git.push(initialized, NEW_BRANCH, True, workdir=SEED_FILE) is None


# ── the hub Run never commits a gitlink pointer move (AD-14, 2026-09-23) ────


def test_a_dirty_submodule_pointer_is_never_swept_into_an_everything_stage(
    git: SubprocessGit, initialized: Path
) -> None:
    """AD-14's own words: "the hub Run never commits gitlink pointer moves — the hub-side
    `git.commit` (no `workdir`) stages the spec folder only, and a submodule pointer is not
    spec content". `stage`'s gitlink exclusion is what makes that true with no `workdir`
    involved at all: the submodule's HEAD moves (dirtying the hub's own gitlink), and an
    ordinary `git add -A` at the worktree root still excludes it."""
    submodule = initialized / WORKDIR
    (submodule / "work.txt").write_text("agent work\n")
    run_git("add", "--all", cwd=submodule)
    run_git("commit", "--quiet", "--message", "agent work", cwd=submodule)
    (initialized / "hub_change.txt").write_text("hub work\n")

    git.stage(initialized)

    staged = run_git("diff", "--cached", "--name-only", cwd=initialized).split()
    assert staged == ["hub_change.txt"]
    assert WORKDIR not in staged


# ── submodule_path: the read-only probe (H6 defect fix, 2026-09-23) ─────────


def test_the_probe_answers_the_repository_relative_path_of_an_initialized_submodule(
    git: SubprocessGit, initialized: Path
) -> None:
    assert git.submodule_path(initialized, WORKDIR) == WORKDIR


def test_the_probe_normalises_the_spellings_a_template_may_differ_in(
    git: SubprocessGit, initialized: Path
) -> None:
    """One answer for `./repos/member`, `repos/member/` and `repos/member`, so a caller
    comparing it with a Template's value compares one string."""
    assert git.submodule_path(initialized, f"./{WORKDIR}/") == WORKDIR


def test_the_probe_answers_none_for_a_path_that_is_not_a_submodule_at_all(
    git: SubprocessGit, initialized: Path
) -> None:
    assert git.submodule_path(initialized, SEED_FILE) is None


def test_the_probe_answers_none_for_a_parent_folder_of_a_submodule(
    git: SubprocessGit, initialized: Path
) -> None:
    """`git submodule status -- repos` answers happily *for the submodule under it*, and
    running a step in `repos` because of that is AD-9's forbidden fall back to a wrong tree."""
    assert git.submodule_path(initialized, "repos") is None


def test_the_probe_answers_none_for_a_submodule_that_was_never_initialized(
    git: SubprocessGit, worktree: Path
) -> None:
    assert git.submodule_path(worktree, WORKDIR) is None


def test_the_probe_leaves_a_submodule_this_run_already_advanced_exactly_where_it_is(
    git: SubprocessGit, initialized: Path
) -> None:
    """The H6 regression, on real git — what `agent_workdir.verify()` does on every `workdir`
    dispatch, in the state an epic's second dispatch actually finds.

    The defect this replaces, reproduced against this very adapter (story H5, confirmed here
    2026-09-23): `verify()` asked `submodule_update`, and `git submodule update` in default
    checkout mode resets the submodule to the commit recorded in the **hub's index** — which
    nothing ever advances, because AD-14 keeps every hub-level commit off the gitlink. So the
    row's own earlier commit (`commit-guard`, inside the member) was undone here: HEAD
    detached at the stale pointer, the file gone from the checkout, and everything the
    dispatch then committed left on an orphan the `git.push` row's branch ref never pointed
    at — while both rows reported `done`.

    Asked twice, because once was never the failing case: it is the *second* dispatch into one
    submodule within a Run that has something to lose."""
    git.submodule_checkout(initialized, WORKDIR, NEW_BRANCH, MEMBER_BASE)
    submodule = initialized / WORKDIR
    (submodule / "work.txt").write_text("agent work\n")
    committed = git.commit(initialized, "story: workdir commit (orchestrator)", workdir=WORKDIR)

    assert git.submodule_path(initialized, WORKDIR) == WORKDIR
    assert git.submodule_path(initialized, WORKDIR) == WORKDIR

    assert branch_of(submodule) == NEW_BRANCH
    assert head_of(submodule) == committed
    assert run_git("rev-parse", f"refs/heads/{NEW_BRANCH}", cwd=submodule).strip() == committed
    assert (submodule / "work.txt").read_text() == "agent work\n"


def test_the_probe_writes_nothing_the_hub_worktree_can_see(
    git: SubprocessGit, initialized: Path
) -> None:
    """Reading only, as an observable fact rather than a claim about which command runs: the
    hub's own porcelain is byte-for-byte what it was, gitlink line included."""
    before = git.status(initialized)

    git.submodule_path(initialized, WORKDIR)

    assert git.status(initialized) == before


# ── status(ignore_submodules=True) ──────────────────────────────────────────
#
# The reuse-when-clean check's own question (AD-14, H7 defect fix 2026-09-24). Only a real
# process settles it: the divergence it must not see is one the hub's index and the member's
# HEAD disagree about, which no scripted porcelain string can be wrong about in the same way.


def advance_the_member(git: SubprocessGit, initialized: Path) -> str:
    """Put the member on the initiative branch and commit in it — what a hub Run does to
    every submodule, and what AD-14 then keeps off the hub's own commits for good."""
    git.submodule_checkout(initialized, WORKDIR, NEW_BRANCH, MEMBER_BASE)
    (initialized / WORKDIR / "work.txt").write_text("agent work\n")
    committed = git.commit(initialized, "story: workdir commit (orchestrator)", workdir=WORKDIR)
    assert committed is not None
    return committed


def test_an_advanced_submodule_is_dirt_only_while_submodule_state_is_counted(
    git: SubprocessGit, initialized: Path
) -> None:
    """The observed defect, on real git: the hub worktree's own tree is untouched, and the
    plain porcelain still says ` M repos/member` — so the reuse check parked `misconfigured`
    on every second Run and on every retry after a park."""
    advance_the_member(git, initialized)

    assert WORKDIR in git.status(initialized)
    assert git.status(initialized, ignore_submodules=True) == ""


def test_a_modified_file_at_the_hub_is_reported_with_submodules_ignored_or_counted(
    git: SubprocessGit, initialized: Path
) -> None:
    """What the exclusion must not cost: only the gitlink leaves the answer. The hub's own
    modification is in both, and it is what still refuses the worktree."""
    advance_the_member(git, initialized)
    (initialized / SEED_FILE).write_text("edited at the hub\n")

    counted = git.status(initialized)
    ignored = git.status(initialized, ignore_submodules=True)

    assert SEED_FILE in counted
    assert SEED_FILE in ignored
    assert WORKDIR in counted
    assert WORKDIR not in ignored
