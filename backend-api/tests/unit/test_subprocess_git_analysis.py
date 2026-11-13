"""The analysis commands of the git adapter against real `git` in `tmp_path` (story 5.1)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from orchestrator.domain.ports.git import Git, GitError
from orchestrator.domain.ports.git_analysis import NameStatus, NumstatEntry
from orchestrator.infrastructure.git.analysis import AnalysisCommands
from orchestrator.infrastructure.git.subprocess_git import SubprocessGit
from tests.unit.test_subprocess_git import BRANCH, TOKEN, run_git


@pytest.fixture(autouse=True)
def git_binary() -> str:
    found = shutil.which("git")
    if found is None:
        pytest.fail("git is not on PATH: this module drives the real adapter.")
    return found


class Repo:
    """A bare origin with `main` holding m0, and a working clone to push from."""

    def __init__(self, root: Path) -> None:
        self.bare = root / "origin.git"
        self.work = root / "work"
        run_git("init", "--quiet", "--bare", str(self.bare), cwd=root)
        self.work.mkdir()
        run_git("init", "--quiet", f"--initial-branch={BRANCH}", ".", cwd=self.work)
        self.url = f"file://{self.bare}"
        self.m0 = self.commit("keep.txt", "one\ntwo\n", "m0")

    def commit(self, name: str, text: str | bytes, message: str) -> str:
        path = self.work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_text(text)
        run_git("add", "--all", cwd=self.work)
        run_git("commit", "--quiet", "--message", message, cwd=self.work)
        return run_git("rev-parse", "HEAD", cwd=self.work).strip()

    def push(self, refspec: str) -> None:
        run_git("push", "--quiet", "--force", self.url, refspec, cwd=self.work)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    made = Repo(tmp_path)
    made.push(f"{BRANCH}:{BRANCH}")
    return made


@pytest.fixture
def git() -> SubprocessGit:
    return SubprocessGit(TOKEN)


@pytest.fixture
def into(tmp_path: Path) -> Path:
    return tmp_path / "scratch" / "analysis" / "root"


def test_the_adapter_still_satisfies_the_port(git: SubprocessGit) -> None:
    adapter: Git = git
    assert adapter is git
    assert isinstance(git, AnalysisCommands)


def test_fetch_into_a_fresh_folder_brings_a_branch_and_a_sha(
    git: SubprocessGit, repo: Repo, into: Path
) -> None:
    head = repo.commit("a.py", "x\n", "c1")
    repo.push(f"{BRANCH}:feature")
    git.fetch(repo.url, (f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}",), into)
    git.fetch(repo.url, (head,), into)
    assert run_git("cat-file", "-t", head, cwd=into).strip() == "commit"
    assert run_git("cat-file", "-t", repo.m0, cwd=into).strip() == "commit"


def test_fetching_an_unknown_sha_is_a_git_error(git: SubprocessGit, repo: Repo, into: Path) -> None:
    with pytest.raises(GitError):
        git.fetch(repo.url, ("0" * 39 + "1",), into)


def test_merge_base_of_a_diverged_pair(git: SubprocessGit, repo: Repo, into: Path) -> None:
    h1 = repo.commit("a.py", "x\n", "h1")
    run_git("checkout", "--quiet", "-b", "other", repo.m0, cwd=repo.work)
    repo.commit("b.py", "y\n", "m1")
    repo.push("other:main")
    git.fetch(repo.url, (f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}",), into)
    repo.push(f"{h1}:refs/heads/feature")
    git.fetch(repo.url, (h1,), into)
    assert git.merge_base(into, h1, "origin/main") == repo.m0


def test_merge_base_without_a_common_ancestor_is_none(
    git: SubprocessGit, repo: Repo, into: Path
) -> None:
    run_git("checkout", "--quiet", "--orphan", "island", cwd=repo.work)
    island = repo.commit("z.txt", "z\n", "island")
    repo.push(f"{island}:refs/heads/island")
    git.fetch(repo.url, (f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}",), into)
    git.fetch(repo.url, (island,), into)
    assert git.merge_base(into, island, "origin/main") is None
    assert git.merge_base(into, "nope", "origin/main") is None


def prepared(git: SubprocessGit, repo: Repo, into: Path) -> tuple[str, str]:
    (repo.work / "bin.dat").write_bytes(b"\x00\x01\x02")
    repo.commit("keep.txt", "one\ntwo\nthree\n", "edit")
    run_git("mv", "keep.txt", "moved.txt", cwd=repo.work)
    repo.commit("bin.dat", b"\x00\x01\x02\x03", "move and binary")
    head = run_git("rev-parse", "HEAD", cwd=repo.work).strip()
    repo.push(f"{head}:refs/heads/feature")
    git.fetch(repo.url, (head,), into)
    return repo.m0, head


def test_numstat_counts_lines_and_flags_a_binary(
    git: SubprocessGit, repo: Repo, into: Path
) -> None:
    base, head = prepared(git, repo, into)
    entries = {e.path: e for e in git.diff_numstat(into, base, head)}
    assert entries["bin.dat"] == NumstatEntry(path="bin.dat", added=0, removed=0, binary=True)
    renamed = [e for e in entries.values() if e.path.endswith("moved.txt")]
    assert len(renamed) == 1
    assert renamed[0].added == 1 and renamed[0].binary is False


def test_name_status_reports_a_rename_with_its_old_path(
    git: SubprocessGit, repo: Repo, into: Path
) -> None:
    base, head = prepared(git, repo, into)
    statuses = git.diff_name_status(into, base, head)
    assert NameStatus(status="R", path="moved.txt", old_path="keep.txt") in statuses
    assert NameStatus(status="A", path="bin.dat", old_path=None) in statuses


def test_diff_text_is_zero_context_and_path_limited(
    git: SubprocessGit, repo: Repo, into: Path
) -> None:
    base, head = prepared(git, repo, into)
    text = git.diff_text(into, base, head, ("moved.txt",))
    assert "+three" in text
    assert "bin.dat" not in text
    assert " two" not in text
    assert "bin.dat" in git.diff_text(into, base, head, ())


def test_commits_between_is_newest_first(git: SubprocessGit, repo: Repo, into: Path) -> None:
    c1 = repo.commit("a.py", "1\n", "c1")
    c2 = repo.commit("a.py", "2\n", "c2")
    repo.push(f"{c2}:refs/heads/feature")
    git.fetch(repo.url, (c2,), into)
    assert git.commits_between(into, repo.m0, c2) == (c2, c1)


def test_an_unknown_ref_answers_the_not_there_values(
    git: SubprocessGit, repo: Repo, into: Path
) -> None:
    git.fetch(repo.url, (f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}",), into)
    assert git.diff_numstat(into, "nope", "nada") == ()
    assert git.diff_name_status(into, "nope", "nada") == ()
    assert git.diff_text(into, "nope", "nada", ()) == ""
    assert git.commits_between(into, "nope", "nada") == ()
