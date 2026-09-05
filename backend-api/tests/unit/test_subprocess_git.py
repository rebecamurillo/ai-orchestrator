"""The git adapter against real `git`, and against local repositories only.

Every repository these tests reach is a bare one this test made in `tmp_path` and registered
by a `file://` URL, so the suite needs the `git` binary and never a network: a unit gate that
depended on github.com would be a gate that goes red when a runner's egress does.

Two claims need a real process rather than a fake. The first is that the commands are the
ones the story names — a blobless clone that checks nothing out, a fetch that moves HEAD
without one, a `show` that reads a file out of a tree — and that each answers "not there"
with `None` rather than an exception. The second is the credential rule (AD-5, hard rule 5):
that the subprocess environment is built rather than inherited, that git is handed the token
through `GIT_ASKPASS` and through nothing else, and that after a clone the token appears in
no file, no config and no remote URL under the work directory.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator.domain.ports.git import Git, GitError
from orchestrator.infrastructure.git.redact import REDACTION
from orchestrator.infrastructure.git.subprocess_git import (
    ASKPASS_NAME,
    ASKPASS_TOKEN_VAR,
    TIMEOUT_SECONDS,
    SubprocessGit,
    command_environment,
    discard_partial_clone,
    tree_bytes,
)


@pytest.fixture(autouse=True)
def git_binary() -> str:
    """`git` is a requirement of this suite, not a condition on running it.

    A `skipif` here would let `make test` pass green on a machine with no git while checking
    none of the credential rule below — and this module is the only place that checks it
    (AD-5). The story lists a missing binary as a blocking condition, so it is one.
    """
    found = shutil.which("git")
    if found is None:
        pytest.fail(
            "git is not on PATH: this module drives the real adapter and is the only gate "
            "that checks the credential rule (AD-5). Install git rather than skipping it."
        )
    return found


TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"
MANIFEST_PATH = "_bmad/_config/manifest.yaml"
MANIFEST = "installation:\n  version: 6.11.0\n"
BRANCH = "main"
ASKPASS_MODE = 0o700
NOT_FOUND_EXIT = 128

#: The per-command budget the story fixes, asserted so it cannot be quietly lowered.
STORY_TIMEOUT_SECONDS = 120


def run_git(*arguments: str, cwd: Path) -> str:
    """Set up a fixture repository. The adapter is what is under test, not this."""
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "e2e",
        "GIT_AUTHOR_EMAIL": "e2e@example.invalid",
        "GIT_COMMITTER_NAME": "e2e",
        "GIT_COMMITTER_EMAIL": "e2e@example.invalid",
    }
    return subprocess.run(  # fixed argv, no shell
        ["git", *arguments], cwd=cwd, env=environment, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """A bare repository with one commit on `main`, carrying a BMAD manifest."""
    bare = tmp_path / "origin.git"
    run_git("init", "--quiet", "--bare", str(bare), cwd=tmp_path)

    seed = tmp_path / "seed"
    seed.mkdir()
    run_git("init", "--quiet", f"--initial-branch={BRANCH}", ".", cwd=seed)
    manifest = seed / MANIFEST_PATH
    manifest.parent.mkdir(parents=True)
    manifest.write_text(MANIFEST)
    run_git("add", "--all", cwd=seed)
    run_git("commit", "--quiet", "--message", "seed", cwd=seed)
    run_git("push", "--quiet", f"file://{bare}", f"{BRANCH}:{BRANCH}", cwd=seed)
    run_git("symbolic-ref", "HEAD", f"refs/heads/{BRANCH}", cwd=bare)
    return bare


@pytest.fixture
def url(origin: Path) -> str:
    return f"file://{origin}"


def bare_holding(tmp_path: Path, name: str, refs: list[str]) -> str:
    """A bare repository holding exactly `refs`, and its `file://` URL."""
    bare = tmp_path / f"{name}.git"
    run_git("init", "--quiet", "--bare", str(bare), cwd=tmp_path)
    seed = tmp_path / f"{name}-seed"
    seed.mkdir()
    run_git("init", "--quiet", f"--initial-branch={BRANCH}", ".", cwd=seed)
    (seed / "README.md").write_text(name)
    run_git("add", "--all", cwd=seed)
    run_git("commit", "--quiet", "--message", "seed", cwd=seed)
    for ref in refs:
        run_git("push", "--quiet", f"file://{bare}", f"{BRANCH}:{ref}", cwd=seed)
    return f"file://{bare}"


@pytest.fixture
def git() -> SubprocessGit:
    return SubprocessGit(TOKEN)


@pytest.fixture
def base(tmp_path: Path) -> Path:
    return tmp_path / "work" / "my-project" / "my-repo" / "base"


def commit_to(origin: Path, tmp_path: Path, name: str) -> str:
    """A second commit on the origin, so a fetch has something to bring back."""
    clone = tmp_path / f"push-{name}"
    run_git("clone", "--quiet", f"file://{origin}", str(clone), cwd=tmp_path)
    (clone / name).write_text(name)
    run_git("add", "--all", cwd=clone)
    run_git("commit", "--quiet", "--message", name, cwd=clone)
    run_git("push", "--quiet", "origin", BRANCH, cwd=clone)
    return run_git("rev-parse", "HEAD", cwd=clone).strip()


# ── the port ─────────────────────────────────────────────────────────────────


def test_the_adapter_satisfies_the_port(git: SubprocessGit) -> None:
    adapter: Git = git

    assert isinstance(adapter, Git)


def test_ls_remote_answers_the_head_the_remote_holds(git: SubprocessGit, url: str) -> None:
    ref = git.ls_remote(url)

    assert ref is not None
    assert ref.ref == "HEAD"
    assert len(ref.sha) == len("0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c")


def test_ls_remote_answers_a_named_branch(git: SubprocessGit, url: str) -> None:
    ref = git.ls_remote(url, BRANCH)

    assert ref is not None
    assert ref.ref == f"refs/heads/{BRANCH}"


def test_ls_remote_answers_none_for_a_ref_the_remote_does_not_hold(
    git: SubprocessGit, url: str
) -> None:
    """A missing branch is an answer, not a failure: line 3 of the check depends on it."""
    assert git.ls_remote(url, "no-such-branch") is None


def test_a_url_that_resolves_to_nothing_is_a_git_error(git: SubprocessGit, tmp_path: Path) -> None:
    with pytest.raises(GitError) as raised:
        git.ls_remote(f"file://{tmp_path}/absent.git")

    assert raised.value.exit_code == NOT_FOUND_EXIT
    assert raised.value.command.startswith("git -c credential.helper= ls-remote")
    assert raised.value.output


# ── a branch is a branch, and nothing that merely looks like one (P3) ────────
#
# The operand git takes here is a glob pattern matched against the tail of a ref on slash
# boundaries, not a name. Asking for `main` is therefore answered by `refs/tags/main` and by
# `refs/heads/release/main` — and a repository holding either of those, but no `main` branch,
# would pass line 3 of the check and then fail the first time a Run tried to work from it.


def test_a_tag_named_like_the_branch_is_not_the_branch(git: SubprocessGit, tmp_path: Path) -> None:
    url = bare_holding(tmp_path, "tagged", ["refs/tags/main", "refs/heads/develop"])

    assert git.ls_remote(url, BRANCH) is None


def test_a_branch_whose_name_merely_ends_with_it_is_not_the_branch(
    git: SubprocessGit, tmp_path: Path
) -> None:
    url = bare_holding(tmp_path, "nested", ["refs/heads/release/main"])

    assert git.ls_remote(url, BRANCH) is None


def test_the_branch_is_still_found_with_both_impostors_beside_it(
    git: SubprocessGit, tmp_path: Path
) -> None:
    """The rule has to exclude the near misses without excluding the real thing."""
    url = bare_holding(
        tmp_path,
        "crowded",
        ["refs/heads/main", "refs/heads/release/main", "refs/tags/main"],
    )

    found = git.ls_remote(url, BRANCH)

    assert found is not None
    assert found.ref == f"refs/heads/{BRANCH}"


def test_a_nested_branch_is_found_by_its_whole_name(git: SubprocessGit, tmp_path: Path) -> None:
    """`release/main` is a legitimate default branch; it is found when it is what was asked."""
    url = bare_holding(tmp_path, "asked", ["refs/heads/release/main"])

    found = git.ls_remote(url, "release/main")

    assert found is not None
    assert found.ref == "refs/heads/release/main"


# ── an operand git cannot read as an option (P5) ─────────────────────────────


def test_a_branch_beginning_with_a_dash_is_an_operand_and_not_an_option(
    git: SubprocessGit, url: str
) -> None:
    """`default_branch` is typed by the Operator; without `--` this would run a program."""
    assert git.ls_remote(url, "--upload-pack=touch /tmp/pwned") is None


def test_a_url_beginning_with_a_dash_is_an_operand_and_not_an_option(
    git: SubprocessGit, base: Path
) -> None:
    """`url` is typed by the Operator, and reaches both `ls-remote` and `clone`."""
    with pytest.raises(GitError):
        git.ls_remote("--upload-pack=touch /tmp/pwned")

    with pytest.raises(GitError):
        git.clone_base("--upload-pack=touch /tmp/pwned", base)


# ── the base clone ───────────────────────────────────────────────────────────


def test_a_base_does_not_exist_before_it_is_cloned(git: SubprocessGit, base: Path) -> None:
    assert git.base_exists(base) is False


def test_a_clone_makes_the_base_and_reports_what_it_wrote(
    git: SubprocessGit, url: str, base: Path
) -> None:
    result = git.clone_base(url, base)

    assert git.base_exists(base) is True
    assert result.bytes > 0
    assert result.seconds >= 0


def test_a_clone_checks_nothing_out(git: SubprocessGit, url: str, base: Path) -> None:
    """`--no-checkout`: the base is history, and Epic 4 adds a worktree per Story."""
    git.clone_base(url, base)

    assert [entry.name for entry in base.iterdir()] == [".git"]


def test_a_clone_creates_the_directories_above_it(git: SubprocessGit, url: str, base: Path) -> None:
    """`/work/{project.slug}/{repository.slug}/base` — nothing else makes those two."""
    assert not base.parent.exists()

    git.clone_base(url, base)

    assert base.parent.is_dir()


def test_a_clone_into_a_path_that_is_already_taken_is_a_git_error(
    git: SubprocessGit, url: str, base: Path
) -> None:
    git.clone_base(url, base)

    with pytest.raises(GitError):
        git.clone_base(url, base)


def test_a_fetch_brings_back_what_was_pushed_after_the_clone(
    git: SubprocessGit, url: str, base: Path, origin: Path, tmp_path: Path
) -> None:
    git.clone_base(url, base)
    pushed = commit_to(origin, tmp_path, "later")

    git.fetch_base(base, BRANCH)

    assert git.read_file(base, BRANCH, "later") == "later"
    assert pushed


def test_a_fetch_points_head_at_the_branch_without_checking_it_out(
    git: SubprocessGit, url: str, base: Path, origin: Path, tmp_path: Path
) -> None:
    git.clone_base(url, base)
    pushed = commit_to(origin, tmp_path, "later")

    git.fetch_base(base, BRANCH)

    assert run_git("rev-parse", "HEAD", cwd=base).strip() == pushed
    assert [entry.name for entry in base.iterdir()] == [".git"]


def test_a_fetch_for_a_branch_the_origin_does_not_hold_leaves_head_alone(
    git: SubprocessGit, url: str, base: Path
) -> None:
    git.clone_base(url, base)
    before = run_git("rev-parse", "HEAD", cwd=base).strip()

    git.fetch_base(base, "no-such-branch")

    assert run_git("rev-parse", "HEAD", cwd=base).strip() == before


def test_a_fetch_in_a_directory_that_is_not_a_clone_is_a_git_error(
    git: SubprocessGit, tmp_path: Path
) -> None:
    with pytest.raises(GitError):
        git.fetch_base(tmp_path, BRANCH)


def test_the_base_knows_the_branch_its_origin_holds(
    git: SubprocessGit, url: str, base: Path
) -> None:
    git.clone_base(url, base)

    assert git.branch_exists(base, BRANCH) is True
    assert git.branch_exists(base, "no-such-branch") is False


# ── reading a file ───────────────────────────────────────────────────────────


def test_a_file_in_the_tree_is_read_at_the_branch(git: SubprocessGit, url: str, base: Path) -> None:
    git.clone_base(url, base)

    assert git.read_file(base, BRANCH, MANIFEST_PATH) == MANIFEST


def test_a_file_that_is_not_in_the_tree_reads_none(
    git: SubprocessGit, url: str, base: Path
) -> None:
    git.clone_base(url, base)

    assert git.read_file(base, BRANCH, "no/such/file.yaml") is None


def test_a_ref_the_clone_does_not_hold_reads_none(git: SubprocessGit, url: str, base: Path) -> None:
    git.clone_base(url, base)

    assert git.read_file(base, "no-such-branch", MANIFEST_PATH) is None


def test_a_file_is_read_from_a_local_ref_when_there_is_no_remote_one(
    git: SubprocessGit, url: str, base: Path
) -> None:
    """`origin/{ref}` is preferred, but a bare sha or a local branch still resolves."""
    git.clone_base(url, base)
    sha = run_git("rev-parse", f"origin/{BRANCH}", cwd=base).strip()

    assert git.read_file(base, sha, MANIFEST_PATH) == MANIFEST


# ── the timeout ──────────────────────────────────────────────────────────────


def test_the_default_timeout_is_the_one_the_story_fixes() -> None:
    assert TIMEOUT_SECONDS == STORY_TIMEOUT_SECONDS


def test_a_command_that_outlives_its_timeout_is_a_failure_that_says_so(
    tmp_path: Path, url: str
) -> None:
    """A timeout that raised something else would reach the Operator as a 500."""
    impatient = SubprocessGit(TOKEN, timeout_seconds=0)

    with pytest.raises(GitError) as raised:
        impatient.ls_remote(url)

    assert raised.value.output == "timeout after 0 s"


def test_a_timeout_is_never_read_as_not_there(tmp_path: Path, url: str, base: Path) -> None:
    """`read_file` answers `None` for a missing file; a command that never ran must not."""
    impatient = SubprocessGit(TOKEN, timeout_seconds=0)

    with pytest.raises(GitError):
        impatient.read_file(base, BRANCH, MANIFEST_PATH)


# ── the credential (AD-5, hard rule 5) ───────────────────────────────────────


def test_the_environment_carries_the_four_variables_git_needs(git: SubprocessGit) -> None:
    environment = command_environment(Path("/tmp/askpass.sh"), Path("/tmp/home"), TOKEN)

    assert environment["GIT_ASKPASS"] == "/tmp/askpass.sh"
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment[ASKPASS_TOKEN_VAR] == TOKEN


def test_the_environment_is_built_and_not_inherited(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hook or a helper git starts must not see this process's other secrets."""
    monkeypatch.setenv("ORCHESTRATOR_SECRET_KEY", "a-key-a-git-hook-must-never-see")

    environment = command_environment(Path("/tmp/askpass.sh"), Path("/tmp/home"), TOKEN)

    assert "ORCHESTRATOR_SECRET_KEY" not in environment
    assert set(environment) == {
        "PATH",
        "HOME",
        "GIT_TERMINAL_PROMPT",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_ASKPASS",
        ASKPASS_TOKEN_VAR,
    }


def test_the_home_is_a_private_empty_directory(git: SubprocessGit) -> None:
    """A user `.gitconfig` could rewrite a URL or install a credential helper."""
    home = Path(command_environment(git._askpass, git._home, TOKEN)["HOME"])

    assert home.is_dir()
    assert list(home.iterdir()) == []


def test_every_command_clears_any_credential_helper(git: SubprocessGit) -> None:
    assert git._command(("ls-remote", "x")) == ["git", "-c", "credential.helper=", "ls-remote", "x"]


def test_the_askpass_script_is_copied_and_executable_by_its_owner_alone(
    git: SubprocessGit,
) -> None:
    """A wheel install does not preserve an executable bit, and git has to run this."""
    assert git._askpass.name == ASKPASS_NAME
    assert git._askpass.stat().st_mode & 0o777 == ASKPASS_MODE
    assert git._askpass.parent != (Path(__file__).parents[2] / "src")


def test_the_askpass_script_prints_the_token_it_is_given(git: SubprocessGit) -> None:
    """The whole mechanism, run the way git runs it."""
    answered = subprocess.run(  # fixed argv, no shell
        [str(git._askpass), "Password for 'https://github.com':"],
        env={"PATH": os.environ.get("PATH", ""), ASKPASS_TOKEN_VAR: TOKEN},
        capture_output=True,
        text=True,
        check=True,
    )

    assert answered.stdout.strip() == TOKEN


def test_the_askpass_script_prints_nothing_else(git: SubprocessGit) -> None:
    answered = subprocess.run(  # fixed argv, no shell
        [str(git._askpass)],
        env={"PATH": os.environ.get("PATH", ""), ASKPASS_TOKEN_VAR: TOKEN},
        capture_output=True,
        text=True,
        check=True,
    )

    assert answered.stdout == f"{TOKEN}\n"
    assert answered.stderr == ""


def test_a_token_that_appears_in_git_output_comes_back_redacted(tmp_path: Path) -> None:
    """The token here is a substring of the path git names in its own failure message."""
    secret = "notarepository"
    adapter = SubprocessGit(secret)

    with pytest.raises(GitError) as raised:
        adapter.ls_remote(f"file://{tmp_path}/{secret}.git")

    assert secret not in raised.value.output
    assert REDACTION in raised.value.output


def test_a_token_that_appears_in_the_command_comes_back_redacted(tmp_path: Path) -> None:
    secret = "notarepository"
    adapter = SubprocessGit(secret)

    with pytest.raises(GitError) as raised:
        adapter.ls_remote(f"file://{tmp_path}/{secret}.git")

    assert secret not in raised.value.command


def test_nothing_under_the_work_directory_holds_the_token(
    git: SubprocessGit, url: str, base: Path
) -> None:
    """The acceptance criterion, checked over every byte the clone wrote."""
    git.clone_base(url, base)
    git.fetch_base(base, BRANCH)

    holders = [
        path for path in base.rglob("*") if path.is_file() and TOKEN.encode() in path.read_bytes()
    ]

    assert holders == []


def test_the_clone_records_the_url_it_was_given_and_no_credential(
    git: SubprocessGit, url: str, base: Path
) -> None:
    git.clone_base(url, base)

    config = (base / ".git" / "config").read_text()

    assert url in config
    assert TOKEN not in config
    assert "askpass" not in config.lower()


# ── what a failed clone leaves behind (P9), and what an adapter does (P10) ───


def test_a_clone_that_fails_leaves_no_half_made_base(tmp_path: Path, url: str, base: Path) -> None:
    """`base_exists` would call a partial directory a clone, and every later check would
    fetch into it instead of cloning again — with no path back."""
    impatient = SubprocessGit(TOKEN, timeout_seconds=0)

    with pytest.raises(GitError):
        impatient.clone_base(url, base)

    assert not base.exists()
    assert impatient.base_exists(base) is False


def test_a_directory_that_was_already_there_is_never_deleted(tmp_path: Path) -> None:
    """Turning a failed clone into data loss would be worse than the state it repairs."""
    dest = tmp_path / "already"
    dest.mkdir()
    (dest / "someones-work.txt").write_text("not this call's to delete")

    discard_partial_clone(dest, existed=True)

    assert (dest / "someones-work.txt").read_text() == "not this call's to delete"


def test_what_the_clone_created_is_what_gets_discarded(tmp_path: Path) -> None:
    dest = tmp_path / "partial"
    (dest / "inner").mkdir(parents=True)
    (dest / "inner" / "half-a-pack").write_text("x")

    discard_partial_clone(dest, existed=False)

    assert not dest.exists()


def test_discarding_a_clone_that_never_started_is_not_an_error(tmp_path: Path) -> None:
    discard_partial_clone(tmp_path / "never-made", existed=False)


def test_an_adapters_private_directory_goes_when_the_adapter_does() -> None:
    """One temporary directory per adapter, and a test builds one per case."""
    adapter = SubprocessGit(TOKEN)
    directory = adapter._askpass.parent
    assert directory.is_dir()

    adapter._cleanup()

    assert not directory.exists()


def test_the_size_of_a_tree_is_what_it_holds(tmp_path: Path) -> None:
    (tmp_path / "a").write_text("12345")
    (tmp_path / "inner").mkdir()
    (tmp_path / "inner" / "b").write_text("678")

    assert tree_bytes(tmp_path) == len("12345") + len("678")
