"""`Git.diff` — one path's unified diff against the worktree (story 6-6, AD-17, FR-31).

`test_git_port.py` covers the port's three frozen values and the fake's scripting; this is
the method 6.6 added, and the two facts a caller is entitled to assume about it: the fake
satisfies the widened protocol, and the adapter builds the command the port describes —
bounded to one path, with git's option parsing ended before it, so a hit whose name begins
with a dash is a pathspec and never a flag.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.domain.ports.git import Git
from orchestrator.infrastructure.git.subprocess_git import SubprocessGit
from tests.unit.fakes.git import FakeGit

WORKTREE = Path("/work/acme/widgets/wt/gates")
SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
UNIFIED = "diff --git a/AGENTS.md b/AGENTS.md\n@@ -1 +1 @@\n-old\n+new\n"


def test_the_fake_still_satisfies_the_widened_port() -> None:
    git: Git = FakeGit()

    assert isinstance(git, Git)


def test_the_fake_answers_the_scripted_diff_and_logs_the_call() -> None:
    git = FakeGit(diff=[UNIFIED])

    answer = git.diff(WORKTREE, SHA, "AGENTS.md")

    assert answer == UNIFIED
    assert git.called("diff") == [(WORKTREE, SHA, "AGENTS.md")]


def test_the_fakes_default_is_the_empty_diff() -> None:
    """ "Not there" is an ordinary answer: a path that did not change is `""`, not an error."""
    assert FakeGit().diff(WORKTREE, SHA, "AGENTS.md") == ""


def test_the_adapter_bounds_the_diff_to_one_path_after_end_of_options(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    recorded: list[tuple[str, ...]] = []
    adapter = SubprocessGit.__new__(SubprocessGit)

    def fake_attempt(*arguments: str) -> str:
        recorded.append(arguments)
        return UNIFIED

    monkeypatch.setattr(adapter, "_attempt", fake_attempt, raising=False)

    assert adapter.diff(WORKTREE, SHA, "-weird.md") == UNIFIED
    assert recorded == [("-C", str(WORKTREE), "diff", SHA, "--", "-weird.md")]


def test_a_ref_the_worktree_does_not_hold_is_the_empty_string(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """`_attempt`'s `None` is the port's own "not there", never a raised failure."""
    adapter = SubprocessGit.__new__(SubprocessGit)
    monkeypatch.setattr(adapter, "_attempt", lambda *_: None, raising=False)

    assert adapter.diff(WORKTREE, SHA, "AGENTS.md") == ""
