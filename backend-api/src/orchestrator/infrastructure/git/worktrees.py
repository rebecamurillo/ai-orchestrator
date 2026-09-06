"""The half of the `Git` adapter a Run's own rows use: worktrees, staging, commits, pushes.

Split out of `subprocess_git.py` for one reason and one only — that module is already 310
lines and `backend-api/AGENTS.md` caps a module at 400 — so this is a mixin over the same
`_run` / `_attempt` / `_remote`, not a second adapter. Every command here therefore inherits
`SubprocessGit`'s whole credential path unchanged (AD-5): the built environment, the private
empty `HOME`, `GIT_ASKPASS`, `-c credential.helper=`, `GIT_TERMINAL_PROMPT=0`, and the
redaction that makes every `GitError.output` safe to store.

Three rules the commands share:

- **`-c core.hooksPath=/dev/null` on everything that writes.** A target repository's own
  hooks are the target repository's; running them under the orchestrator's uid, in the
  orchestrator's container, on a commit the orchestrator composed, is not what an Operator
  asked for and is a straightforward way to run arbitrary code from a cloned repository.
- **The author is the orchestrator, stated per command.** `-c user.name` / `-c user.email`
  rather than a written `.gitconfig`: `HOME` is a private empty directory by design
  (`subprocess_git.py`), so there is nowhere for a stored identity to live, and a commit that
  fell back to git's guessed identity would fail outright in a container with no `/etc/passwd`
  entry to guess from.
- **Absence is not failure, exactly where the port says so.** `sync` answers `None` when the
  branch has no upstream, `head_sha` answers `None` before the first commit, and
  `remove_worktree` / `delete_branch` are content with something that is already gone —
  because `cancel` calls both on a Run whose rows may never have created either (AD-13).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

#: Where a base clone's origin refs live. The same word `subprocess_git.py` uses.
ORIGIN = "origin"

#: The two config values every writing command carries: see the module docstring.
NO_HOOKS = ("-c", "core.hooksPath=/dev/null")
AUTHOR = ("-c", "user.name=orchestrator", "-c", "user.email=orchestrator@local")

#: Ends git's option parsing, before a branch name or a pathspec the Operator's data decided.
END_OF_OPTIONS = "--"

#: What `-z` separates paths with, so a non-ASCII path never has to be unquoted to be used.
NUL = "\0"

#: Everything a `stage` stages when the caller named no pathspec.
EVERYTHING = "-A"


class _Runner(Protocol):
    """The three helpers `SubprocessGit` already has, as this mixin needs to see them."""

    def _run(self, *arguments: str) -> str: ...

    def _attempt(self, *arguments: str) -> str | None: ...

    def _remote(self, branch: str) -> str: ...


class WorktreeCommands:
    """The `Git` port's worktree, commit and push half, over the same `git(1)` invocation."""

    def worktree_add(
        self: _Runner, base: Path, path: Path, branch: str, start_point: str | None
    ) -> str:
        """`git worktree add` — tracking the origin's branch, or creating it at a start point.

        The base clone's `HEAD` is detached first, which AD-14 asks for in as many words: "a
        detached `HEAD`, so any branch, the default one included, can be added as a worktree".
        A clone leaves `HEAD` symbolic on the default branch, and git refuses to check a
        branch out into a worktree while another worktree — the base clone itself — has it,
        so an `epic@1` whose branch *is* the default branch would fail on its checkout row.
        Idempotent: a `HEAD` that is already detached is written back unchanged.
        """
        head = self._attempt("-C", str(base), "rev-parse", "--verify", "--quiet", "HEAD")
        if head is not None:
            self._run("-C", str(base), "update-ref", "--no-deref", "HEAD", head.strip())
        path.parent.mkdir(parents=True, exist_ok=True)
        if start_point is None:
            return self._run(
                "-C", str(base), *NO_HOOKS, "worktree", "add", str(path), END_OF_OPTIONS, branch
            )
        return self._run(
            "-C",
            str(base),
            *NO_HOOKS,
            "worktree",
            "add",
            "-b",
            branch,
            str(path),
            END_OF_OPTIONS,
            start_point,
        )

    def sync(self: _Runner, worktree: Path, branch: str) -> str | None:
        """Fetch the branch and fast-forward onto it; `None` when the origin does not hold it.

        **The upstream question is asked of the remote, not of the local config.** AD-14 words
        it as `rev-parse --abbrev-ref @{upstream}` failing, and that is the *case* it means —
        a branch this Run created and has never pushed. It is not the *command*: `git worktree
        add -b {branch} … origin/{base}` sets the new branch's upstream to `origin/{base}`, so
        `@{upstream}` answers happily for exactly the branch that was never pushed, and the
        fetch after it would then fail on a ref the remote does not hold. `ls-remote --heads`
        asks what the rule is actually about, and answers it for both cases.

        `merge --ff-only FETCH_HEAD` rather than `pull --ff-only`, for the same reason: a pull
        needs the tracking configuration this branch may not have, and what the row does is
        take what the remote already has. A history that will not fast-forward raises the
        `GitError` the caller parks the Run on.
        """
        held = self._attempt(
            "-C", str(worktree), "ls-remote", "--heads", ORIGIN, END_OF_OPTIONS, branch
        )
        if not (held or "").strip():
            return None
        fetched = self._run("-C", str(worktree), "fetch", ORIGIN, END_OF_OPTIONS, branch)
        merged = self._run("-C", str(worktree), *NO_HOOKS, "merge", "--ff-only", "FETCH_HEAD")
        return fetched + merged

    def status(self: _Runner, worktree: Path) -> str:
        """`git status --porcelain`: the empty string when the worktree is clean."""
        return self._run("-C", str(worktree), "status", "--porcelain")

    def stage(self: _Runner, worktree: Path, pathspec: str | None = None) -> None:
        """`git add -A`, over everything or over one pathspec the caller named."""
        arguments = ("-C", str(worktree), "add", EVERYTHING)
        if pathspec is None:
            self._run(*arguments)
            return
        self._run(*arguments, END_OF_OPTIONS, pathspec)

    def commit(self: _Runner, worktree: Path, message: str) -> str:
        """Commit what is staged as the orchestrator, and answer with the new commit."""
        self._run(
            "-C",
            str(worktree),
            *NO_HOOKS,
            *AUTHOR,
            "commit",
            "--message",
            message,
        )
        return self._run("-C", str(worktree), "rev-parse", "HEAD").strip()

    def diff_names(self: _Runner, worktree: Path, from_sha: str) -> tuple[str, ...]:
        """Every path that changed between `from_sha` and the worktree as it stands.

        `HEAD` and the index and the untracked files all matter to AD-17, and `diff --name-only`
        alone would miss the last of them, so the two answers are unioned. `-z` for the reason
        `list_files` uses it: a quoted non-ASCII path would not match the glob it should.
        """
        changed = self._attempt(
            "-C", str(worktree), "diff", "--name-only", "-z", from_sha, END_OF_OPTIONS
        )
        untracked = self._run(
            "-C", str(worktree), "ls-files", "--others", "--exclude-standard", "-z"
        )
        names = f"{changed or ''}{NUL}{untracked}".split(NUL)
        return tuple(dict.fromkeys(name for name in names if name))

    def push(self: _Runner, worktree: Path, branch: str, set_upstream: bool) -> str:
        """`git push origin {branch}`, with `-u` when this Run created the branch. Never forced."""
        upstream = ("--set-upstream",) if set_upstream else ()
        return self._run("-C", str(worktree), "push", *upstream, ORIGIN, END_OF_OPTIONS, branch)

    def head_sha(self: _Runner, path: Path) -> str | None:
        """The commit `HEAD` points at, or `None` where there is not one yet."""
        answer = self._attempt("-C", str(path), "rev-parse", "--verify", "--quiet", "HEAD")
        return answer.strip() if answer is not None else None

    def remove_worktree(self: _Runner, base: Path, path: Path) -> None:
        """Remove the worktree, then prune the record; one already gone is not a failure.

        `--force` here is not the dangerous kind: it is what lets `cancel` remove a worktree
        the Operator abandoned dirty, which is the whole case AD-13 asks this for.
        """
        self._attempt("-C", str(base), "worktree", "remove", "--force", str(path))
        self._attempt("-C", str(base), "worktree", "prune")

    def delete_branch(self: _Runner, base: Path, branch: str) -> None:
        """Delete the local branch; one already gone is not a failure (AD-13's `cancel`)."""
        self._attempt("-C", str(base), "branch", "-D", END_OF_OPTIONS, branch)
