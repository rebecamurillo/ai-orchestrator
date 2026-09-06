"""`PlanReader`: the planner's one door to `Git`, and the reason it only knocks once.

`plan_run` is pure apart from three calls — `ls_remote`, `read_file`, `list_files` — and
they all go through this object. Two things follow from that.

**FR-10 becomes checkable.** "Each list file is read once per Run" is a property of the
memo below rather than of the walker: the walker asks for the same `(ref, path)` as often
as the tree makes it ask, and this turns those into one `Git` call, which a test settles by
reading `FakeGit.calls` instead of by reading the walker.

**A negative answer is memoised too.** A branch the remote does not hold and a file the
tree does not carry are ordinary answers (the `Git` port's second convention), and re-asking
for them would be a call per Story rather than a call per Run.

`record` is deliberately not part of `read`: `Run.plan_refs` holds the commit each *list
file* was read at, so a plan can be called stale, and a story file — read at its frame's
ref, never the thing that makes a plan stale — records nothing.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.domain.ports.git import Git


class PlanReader:
    """Memoised reads of one base clone, and the list-file commits worth remembering."""

    def __init__(self, git: Git, *, base: Path, url: str) -> None:
        self._git = git
        self._base = base
        self._url = url
        #: `{path: sha}` — what `Plan.plan_refs` is built from.
        self.plan_refs: dict[str, str] = {}
        self._shas: dict[str, str | None] = {}
        self._files: dict[tuple[str, str], str | None] = {}
        self._listings: dict[tuple[str, str], tuple[str, ...]] = {}

    def sha(self, branch: str) -> str | None:
        """The commit `origin/{branch}` resolves to, or `None` when the remote has none."""
        if branch not in self._shas:
            found = self._git.ls_remote(self._url, branch)
            self._shas[branch] = None if found is None else found.sha
        return self._shas[branch]

    def read(self, ref: str, path: str) -> str | None:
        """One file's text at a ref, or `None` when the tree does not hold it."""
        key = (ref, path)
        if key not in self._files:
            self._files[key] = self._git.read_file(self._base, ref, path)
        return self._files[key]

    def listing(self, ref: str, prefix: str) -> tuple[str, ...]:
        """Every path under a prefix at a ref; `()` when there is nothing there."""
        key = (ref, prefix)
        if key not in self._listings:
            self._listings[key] = self._git.list_files(self._base, ref, prefix)
        return self._listings[key]

    def record(self, path: str, sha: str) -> None:
        """Remember which commit a list file was read at (`Run.plan_refs`)."""
        self.plan_refs[path] = sha
