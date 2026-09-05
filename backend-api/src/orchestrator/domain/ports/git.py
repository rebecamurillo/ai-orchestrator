"""The `Git` port: every command this system runs against a repository, named once.

`domain/` and `application/` may not import `subprocess`, `os` or `shutil` (AD-2), so the
rules that decide *what* to run take this protocol and the adapter in
`infrastructure/git/subprocess_git.py` decides *how*. The same protocol is what
`tests/unit/fakes/git.py` implements, which is why the clone check is covered without a
network and without a process.

Three conventions hold for every method:

- **A failure is a `GitError`**, carrying the command, its exit code and its output. A
  method never returns a status code for the caller to interpret, and never swallows a
  failure into a falsy value.
- **"Not there" is `None` or `False`**, not an error. A ref that does not exist on the
  remote, a file that is not in the tree and a base clone that has not been made yet are
  ordinary answers, and the rules above decide what each of them means.
- **A path is a `Path` the caller composed.** Nothing here reads `WORK_DIR`; the use case is
  given `work_dir` and builds `{work_dir}/{project.slug}/{repository.slug}/base` (AD-14).

`base_exists` is the reason the use case can choose between a clone and a fetch without
touching the filesystem itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RemoteRef:
    """One ref a remote answered with, and the commit it resolves to."""

    ref: str
    sha: str


@dataclass(frozen=True)
class CloneResult:
    """What making a base clone cost: how long the adapter took, and what it wrote."""

    seconds: float
    bytes: int


class GitError(Exception):
    """A git command that failed, as the rules above are allowed to see it.

    `output` is already redacted by the adapter (AD-5): a credential that appeared in git's
    own message is `***` by the time it reaches this object, so a caller storing it verbatim
    — which is exactly what the clone check does — cannot leak one.
    """

    def __init__(self, *, command: str, exit_code: int, output: str) -> None:
        super().__init__(f"{command} exited {exit_code}: {output}")
        self.command = command
        self.exit_code = exit_code
        self.output = output


@runtime_checkable
class Git(Protocol):
    """The git commands this system runs. Later stories extend it; none of them narrow it."""

    def ls_remote(self, url: str, ref: str | None = None) -> RemoteRef | None:
        """The ref the remote answers with, or `None` when it holds no such ref.

        Without a `ref` this asks for `HEAD`, which is the cheapest proof that the URL
        resolves and the credential is accepted.

        With one, `ref` names a **branch**, and only a branch of exactly that name matches.
        Not a tag of the same name, and not a branch whose name merely ends with it — a
        repository holding `release/main` does not hold `main`. The distinction is the whole
        value of the check: a match that was only near would pass here and fail the first
        time a Run tried to work from the branch.
        """
        ...

    def base_exists(self, dest: Path) -> bool:
        """Whether a base clone has already been made at this path."""
        ...

    def clone_base(self, url: str, dest: Path) -> CloneResult:
        """Make the blobless, un-checked-out base clone, and report what it cost."""
        ...

    def fetch_base(self, dest: Path, branch: str) -> None:
        """Bring an existing base clone up to date with its origin."""
        ...

    def branch_exists(self, dest: Path, branch: str) -> bool:
        """Whether the base clone knows this branch on its origin."""
        ...

    def read_file(self, dest: Path, ref: str, path: str) -> str | None:
        """One file's text out of the base clone at a ref, or `None` when it is not there."""
        ...
