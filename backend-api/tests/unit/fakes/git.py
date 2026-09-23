"""In-memory `Git` — the one fake for that port (AD-18). Reuse it; do not write another.

It scripts answers rather than simulating git: each method takes a list of what to answer,
in order, and an entry that is an exception is raised instead of returned. Running past the
end of a list repeats the last entry, so a test that scripted one answer is asserting that
answer and not the length of a list.

Any exception, not only a `GitError`: the adapter also raises `OSError` on ordinary paths —
an unwritable `WORK_DIR`, a `git` that is not on `PATH` — and a fake that could only express
git's own refusals would leave the rule that turns those into a failed line untested.

Two properties are copied from the adapter, because a use case tested against a weaker
double would pass here and fail against a real process:

- **Every call is recorded, with its arguments.** "`fetch_base` was called and `clone_base`
  was not" is a rule of the clone check, and only a call log can settle it.
- **A command takes time.** The adapter's line durations come from the `Clock`, so this fake
  advances the `FakeClock` it is given by `seconds` on every call. Without that a line's
  `seconds` would be zero for every scenario and nothing would be asserting them.

4.8 completed the port, so the worktree half is scripted the same way: `worktree_add`,
`sync`, `merge` (S4), `status`, `stage`, `commit`, `diff_names`, `diff_changes`, `diff` (6.6),
`push`, `head_sha`, `remove_worktree` and `delete_branch` each take a list, an entry that is
an exception is raised, and every call is logged with its arguments — which is what lets "the
spec folder was staged before everything else" and "no push command ran" be assertions rather
than hopes. H1's `submodule_update` and `submodule_checkout` are scripted the same way; the
second one's `None` is the port's "not an initialized submodule", which is the one answer a
test has to ask for on purpose because it is the one that parks the Run.

The planner asks the same three questions of many refs and paths, and "which answer came
back" matters more to it than "how many answers were scripted", so three of the methods
also take a **mapping**: `refs` (branch -> sha), `files` (`(ref, path)` -> text) and
`listings` (`(ref, prefix)` -> paths). A mapping that is not given is not used, so every
caller written against the sequential script keeps exactly the behaviour it had; a key a
mapping does not hold is the port's own "not there" — `None`, `None` and `()`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrator.domain.ports.git import Change, CloneResult, RemoteRef
from tests.unit.fakes.clock import FakeClock

#: The answers a reachable repository with no BMAD manifest gives.
DEFAULT_SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
DEFAULT_REF = RemoteRef(ref="HEAD", sha=DEFAULT_SHA)
DEFAULT_CLONE = CloneResult(seconds=1.0, bytes=4096)

#: What `push_branch` answers when it created the branch — git's own words for it. `None`
#: is the other answer, and it means the remote already held it (adopted, AD-14, S6).
DEFAULT_PUSH_BRANCH = "* [new branch]"

#: What `submodule_update` answers for a worktree holding none — the ordinary case for
#: every Run that is not a hub Run (AD-14, story H1).
DEFAULT_SUBMODULES: tuple[str, ...] = ()


class FakeGit:
    """Scripted answers, a call log, and a clock that moves once per command."""

    def __init__(  # noqa: PLR0913 — one keyword per port method, each optional
        self,
        *,
        clock: FakeClock | None = None,
        seconds: float = 0.0,
        ls_remote: list[Any] | None = None,
        base_exists: list[Any] | None = None,
        clone_base: list[Any] | None = None,
        fetch_base: list[Any] | None = None,
        branch_exists: list[Any] | None = None,
        read_file: list[Any] | None = None,
        list_files: list[Any] | None = None,
        worktree_add: list[Any] | None = None,
        sync: list[Any] | None = None,
        merge: list[Any] | None = None,
        status: list[Any] | None = None,
        stage: list[Any] | None = None,
        commit: list[Any] | None = None,
        diff_names: list[Any] | None = None,
        diff_changes: list[Any] | None = None,
        diff: list[Any] | None = None,
        push: list[Any] | None = None,
        push_branch: list[Any] | None = None,
        submodule_update: list[Any] | None = None,
        submodule_checkout: list[Any] | None = None,
        head_sha: list[Any] | None = None,
        remove_worktree: list[Any] | None = None,
        delete_branch: list[Any] | None = None,
        refs: dict[str, str] | None = None,
        files: dict[tuple[str, str], str] | None = None,
        listings: dict[tuple[str, str], list[str]] | None = None,
    ) -> None:
        self.clock = clock
        self.seconds = seconds
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.refs = refs
        self.files = files
        self.listings = listings
        self._scripts: dict[str, list[Any]] = {
            "ls_remote": ls_remote or [DEFAULT_REF],
            "base_exists": base_exists or [False],
            "clone_base": clone_base or [DEFAULT_CLONE],
            "fetch_base": fetch_base or [None],
            "branch_exists": branch_exists or [True],
            "read_file": read_file or [None],
            "list_files": list_files or [()],
            "worktree_add": worktree_add or [""],
            "sync": sync or [""],
            # `None` rather than a sha: a fake nobody scripted has nothing to merge, which
            # is the answer that changes no branch (`already merged`, S4).
            "merge": merge if merge is not None else [None],
            "status": status or [""],
            "stage": stage or [None],
            "commit": commit or [DEFAULT_SHA],
            "diff_names": diff_names or [()],
            "diff_changes": diff_changes or [()],
            "diff": diff or [""],
            "push": push or [""],
            "push_branch": push_branch or [DEFAULT_PUSH_BRANCH],
            # `()` rather than a path: a fake nobody scripted stands in a worktree with no
            # submodules, which is every Run that is not a hub Run (H1).
            "submodule_update": (
                submodule_update if submodule_update is not None else [DEFAULT_SUBMODULES]
            ),
            # a sha rather than `None`: `None` is the one answer that carries a park —
            # "not an initialized submodule" — so it is never the unscripted default (H1).
            "submodule_checkout": submodule_checkout or [DEFAULT_SHA],
            "head_sha": head_sha or [DEFAULT_SHA],
            "remove_worktree": remove_worktree or [None],
            "delete_branch": delete_branch or [None],
        }
        self._used: dict[str, int] = dict.fromkeys(self._scripts, 0)

    # ── the port ─────────────────────────────────────────────────────────────

    def ls_remote(self, url: str, ref: str | None = None) -> RemoteRef | None:
        if self.refs is not None and ref is not None:
            self._record("ls_remote", (url, ref))
            return _remote_ref(ref, self.refs.get(ref))
        answer: RemoteRef | None = self._answer("ls_remote", (url, ref))
        return answer

    def base_exists(self, dest: Path) -> bool:
        answer: bool = self._answer("base_exists", (dest,))
        return answer

    def clone_base(self, url: str, dest: Path) -> CloneResult:
        answer: CloneResult = self._answer("clone_base", (url, dest))
        return answer

    def fetch_base(self, dest: Path, branch: str) -> None:
        self._answer("fetch_base", (dest, branch))

    def branch_exists(self, dest: Path, branch: str) -> bool:
        answer: bool = self._answer("branch_exists", (dest, branch))
        return answer

    def read_file(self, dest: Path, ref: str, path: str) -> str | None:
        if self.files is not None:
            self._record("read_file", (dest, ref, path))
            return self.files.get((ref, path))
        answer: str | None = self._answer("read_file", (dest, ref, path))
        return answer

    def list_files(self, dest: Path, ref: str, prefix: str) -> tuple[str, ...]:
        if self.listings is not None:
            self._record("list_files", (dest, ref, prefix))
            return tuple(self.listings.get((ref, prefix), ()))
        answer: tuple[str, ...] = self._answer("list_files", (dest, ref, prefix))
        return answer

    # ── the worktree half (4.8) ──────────────────────────────────────────────

    def worktree_add(self, base: Path, path: Path, branch: str, start_point: str | None) -> str:
        answer: str = self._answer("worktree_add", (base, path, branch, start_point))
        return answer

    def sync(self, worktree: Path, branch: str) -> str | None:
        answer: str | None = self._answer("sync", (worktree, branch))
        return answer

    def merge(self, worktree: Path, branch: str) -> str | None:
        answer: str | None = self._answer("merge", (worktree, branch))
        return answer

    def status(self, worktree: Path) -> str:
        answer: str = self._answer("status", (worktree,))
        return answer

    def stage(self, worktree: Path, pathspec: str | None = None) -> None:
        self._answer("stage", (worktree, pathspec))

    def commit(self, worktree: Path, message: str) -> str:
        answer: str = self._answer("commit", (worktree, message))
        return answer

    def diff_names(self, worktree: Path, from_sha: str) -> tuple[str, ...]:
        answer: tuple[str, ...] = self._answer("diff_names", (worktree, from_sha))
        return answer

    def diff_changes(self, worktree: Path, from_sha: str, to_sha: str) -> tuple[Change, ...]:
        answer: tuple[Change, ...] = self._answer("diff_changes", (worktree, from_sha, to_sha))
        return answer

    def diff(self, worktree: Path, from_sha: str, path: str) -> str:
        answer: str = self._answer("diff", (worktree, from_sha, path))
        return answer

    def push(self, worktree: Path, branch: str, set_upstream: bool) -> str:
        answer: str = self._answer("push", (worktree, branch, set_upstream))
        return answer

    def push_branch(self, dest_base: Path, branch: str, at_ref: str) -> str | None:
        """Adopt-or-create, against the `refs` map when there is one (multi-repo S6).

        With a `refs` map the fake answers the adapter's own rule rather than a script — a
        branch the map already holds is adopted (`None`), one it does not is created — and
        **records the creation in the map**, because that is what the real remote does and
        because the very next thing dispatch does is plan an epic Run off that branch. A
        caller that scripted `push_branch` instead gets its script, like every other method.
        """
        if self.refs is not None:
            self._record("push_branch", (dest_base, branch, at_ref))
            if self.refs.get(branch):
                return None
            self.refs[branch] = at_ref
            return DEFAULT_PUSH_BRANCH
        answer: str | None = self._answer("push_branch", (dest_base, branch, at_ref))
        return answer

    # ── the submodule half (H1) ──────────────────────────────────────────────

    def submodule_update(self, worktree: Path) -> tuple[str, ...]:
        answer: tuple[str, ...] = self._answer("submodule_update", (worktree,))
        return answer

    def submodule_checkout(
        self, worktree: Path, workdir: str, branch: str, base: str | None = None
    ) -> str | None:
        answer: str | None = self._answer("submodule_checkout", (worktree, workdir, branch, base))
        return answer

    def head_sha(self, path: Path) -> str | None:
        answer: str | None = self._answer("head_sha", (path,))
        return answer

    def remove_worktree(self, base: Path, path: Path) -> None:
        self._answer("remove_worktree", (base, path))

    def delete_branch(self, base: Path, branch: str) -> None:
        self._answer("delete_branch", (base, branch))

    # ── the script ───────────────────────────────────────────────────────────

    def _record(self, method: str, arguments: tuple[Any, ...]) -> None:
        """Every call is logged and every call costs time, scripted or answered by a map."""
        self.calls.append((method, arguments))
        if self.clock is not None:
            self.clock.advance(self.seconds)

    def _answer(self, method: str, arguments: tuple[Any, ...]) -> Any:
        self._record(method, arguments)
        script = self._scripts[method]
        index = min(self._used[method], len(script) - 1)
        self._used[method] = index + 1
        answer = script[index]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def called(self, method: str) -> list[tuple[Any, ...]]:
        """The arguments every call to one method was made with."""
        return [arguments for name, arguments in self.calls if name == method]


def _remote_ref(branch: str, sha: str | None) -> RemoteRef | None:
    """What `ls_remote` answers for a mapped branch: the full ref name, or nothing."""
    if sha is None:
        return None
    return RemoteRef(ref=f"refs/heads/{branch}", sha=sha)
