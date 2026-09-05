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
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrator.domain.ports.git import CloneResult, RemoteRef
from tests.unit.fakes.clock import FakeClock

#: The answers a reachable repository with no BMAD manifest gives.
DEFAULT_SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
DEFAULT_REF = RemoteRef(ref="HEAD", sha=DEFAULT_SHA)
DEFAULT_CLONE = CloneResult(seconds=1.0, bytes=4096)


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
    ) -> None:
        self.clock = clock
        self.seconds = seconds
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._scripts: dict[str, list[Any]] = {
            "ls_remote": ls_remote or [DEFAULT_REF],
            "base_exists": base_exists or [False],
            "clone_base": clone_base or [DEFAULT_CLONE],
            "fetch_base": fetch_base or [None],
            "branch_exists": branch_exists or [True],
            "read_file": read_file or [None],
        }
        self._used: dict[str, int] = dict.fromkeys(self._scripts, 0)

    # ── the port ─────────────────────────────────────────────────────────────

    def ls_remote(self, url: str, ref: str | None = None) -> RemoteRef | None:
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
        answer: str | None = self._answer("read_file", (dest, ref, path))
        return answer

    # ── the script ───────────────────────────────────────────────────────────

    def _answer(self, method: str, arguments: tuple[Any, ...]) -> Any:
        self.calls.append((method, arguments))
        if self.clock is not None:
            self.clock.advance(self.seconds)
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
