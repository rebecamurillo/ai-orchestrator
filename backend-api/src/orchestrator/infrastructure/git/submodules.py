"""The `Git` adapter's submodule half: a hub Run's `repos/*` as working folders (AD-14).

A third mixin over the same `_run` / `_attempt` that `subprocess_git.py` owns, split out for
the reason `worktrees.py` was — the 400-line cap — and inheriting that module's whole
credential path unchanged (AD-5): the built environment, the private empty `HOME`,
`GIT_ASKPASS`, `-c credential.helper=`, `GIT_TERMINAL_PROMPT=0`, and the redaction that makes
every `GitError.output` safe to store. A member repository may be private, which is why these
are orchestrator step kinds at all and never template `shell` commands (AD-14): a harness or
a `shell` row never receives `GITHUB_TOKEN`.

**The credential reaches the child processes, and that is not an assumption.** `git submodule
update` clones and fetches in child processes of the command this adapter started, and a
child inherits its parent's environment — so `GIT_ASKPASS` covers the `https` URLs
`.gitmodules` holds without anything being passed down explicitly.
`tests/unit/test_subprocess_git_submodules.py` observes the environment such a child actually
runs with rather than asserting the principle.

**What a linked worktree does with submodules, found empirically (story H1, 2026-09-23).**
Every tree this system works in is a linked worktree of a base clone, and git puts a linked
worktree's submodule git directory under `base/.git/worktrees/{worktree}/modules/{name}` —
*not* under the shared `base/.git/modules/`. Each worktree therefore has its own checkout of
the same submodule, with its own HEAD and its own branches, which is what makes AD-14's "a
submodule is a working folder inside a worktree, never a second workspace" true rather than
hopeful: two Runs on two branches of one hub repository cannot move each other's member
checkout. What *is* shared is the base clone's config, where `submodule.{name}.url` is
recorded — the same URL for every worktree of one repository, and a second `init` leaves an
already-recorded one alone, so the sharing is idempotent rather than a race.

**Nothing here relaxes `protocol.file.allow`.** git refuses the `file` transport for a clone
a submodule started (CVE-2022-39253) and a real member repository is `https`; the test suite
allows it for its own `file://` fixture through the adapter's private `HOME`, which is the
fixture's business and never the adapter's.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Protocol

from orchestrator.infrastructure.git.worktrees import (
    AUTHOR,
    END_OF_OPTIONS,
    EVERYTHING,
    HEADS_NAMESPACE,
    NO_HOOKS,
    NUL,
    ORIGIN,
    RAW_PATHS,
    UNTRACKED_ALL,
)

#: What `git submodule status` writes in column 1 for a submodule that is not initialized —
#: a gitlink with an empty folder under it, which is not a workdir any step can run in.
UNINITIALIZED = "-"

#: The local ref a plain clone records for the remote's own default branch, and the prefix
#: `submodule_default_branch` strips off it to answer with the branch name alone (H2).
ORIGIN_HEAD = "refs/remotes/origin/HEAD"
ORIGIN_HEAD_NAMESPACE = "refs/remotes/origin/"

#: What `ls-files -s` writes in the mode column for a gitlink — a submodule pointer, the same
#: marker for every submodule whether or not it is initialized. `_gitlink_paths` reads this so
#: `WorktreeCommands.stage` never sweeps a pointer move into a hub commit (AD-14, H2).
GITLINK_MODE = "160000"

#: How git closes a `submodule status` line: `{flag}{sha} {path} ({describe})`. The describe
#: part is optional, so the path is what is left once it is taken off the end.
DESCRIBE_OPENER = " ("
DESCRIBE_CLOSER = ")"


#: `SubprocessGit._attempt`, as the readers below need to see it: a command whose non-zero
#: exit means "not there" rather than "broken". The same alias `worktrees.py` declares.
_Attempt = Callable[..., "str | None"]


class _Runner(Protocol):
    """The two helpers `SubprocessGit` already has, as this mixin needs to see them."""

    def _run(self, *arguments: str) -> str: ...

    def _attempt(self, *arguments: str) -> str | None: ...


class SubmoduleCommands:
    """The `Git` port's submodule half, over the same `git(1)` invocation."""

    def submodule_update(self: _Runner, worktree: Path) -> tuple[str, ...]:
        """`git submodule update --init --recursive`, then report what is initialized.

        `--recursive` because a member repository may carry submodules of its own and a
        half-materialised tree is not a working folder. The answer is read back from git
        rather than from `.gitmodules`: a submodule the update could not or would not
        initialize (`submodule.{name}.update = none`, an inactive one) is a gitlink with an
        empty folder under it, and calling that a workdir is what AD-9's
        `not an initialized submodule` stop exists to prevent.

        Idempotent by construction: `update` re-runs to the same recorded commits, and the
        listing after it is the same listing.
        """
        self._run("-C", str(worktree), *NO_HOOKS, "submodule", "update", "--init", "--recursive")
        return tuple(_initialized(self._attempt, worktree, recursive=True))

    def submodule_checkout(
        self: _Runner, worktree: Path, workdir: str, branch: str, base: str | None = None
    ) -> str | None:
        """Create or check out `branch` inside one submodule, with its upstream set.

        The order is the rule. **The workdir is settled before anything is written**: a path
        that is not an initialized submodule is `None` and no command runs in it, so the
        executor's park is a decision about a tree nothing has touched. **The fetch comes
        next**, because every question after it — does the member's remote hold this branch,
        does the declared base exist there, can this branch fast-forward — is a question
        about the remote's refs as they stand now.

        **A local branch is checked out, never re-cut.** `-B` would reset it to the start
        point, and by the time an epic's second row runs, that branch is carrying commits the
        agent made inside the submodule. So an existing branch is checked out as it is and
        then fast-forwarded *if it can be* (`_attempt`, not `_run`): a branch that diverged
        from the member's remote is a fact for a later `git.push` row to park on, not a
        reason for this row to refuse.

        **The upstream is written as config, not with `--set-upstream-to`.** AD-14 asks for
        "upstream set" on a branch the member's remote may not hold yet, and
        `branch --set-upstream-to=origin/{branch}` fails outright when that ref does not
        exist. `branch.{branch}.remote` + `branch.{branch}.merge` is the same two values
        git would have written, configured for the push that will create the remote branch.
        """
        submodule = _submodule_dir(self._attempt, worktree, workdir)
        if submodule is None:
            return None
        self._run("-C", str(submodule), "fetch", ORIGIN)
        held = _remote_head(self._attempt, submodule, branch)
        if _local_branch(self._attempt, submodule, branch) is None:
            start = held or _remote_head(self._attempt, submodule, base) or "HEAD"
            self._run("-C", str(submodule), *NO_HOOKS, "checkout", "--quiet", "-b", branch, start)
        else:
            self._run(
                "-C", str(submodule), *NO_HOOKS, "checkout", "--quiet", branch, END_OF_OPTIONS
            )
        if held is not None:
            self._attempt(
                "-C", str(submodule), *NO_HOOKS, "merge", "--ff-only", f"{ORIGIN}/{branch}"
            )
        self._run("-C", str(submodule), "config", f"branch.{branch}.remote", ORIGIN)
        self._run(
            "-C", str(submodule), "config", f"branch.{branch}.merge", f"{HEADS_NAMESPACE}{branch}"
        )
        return self._run("-C", str(submodule), "rev-parse", "HEAD").strip()

    def submodule_default_branch(self: _Runner, worktree: Path, workdir: str) -> str | None:
        """The submodule's own default branch, read from its recorded `origin/HEAD`.

        AD-14's own words (ratified 2026-09-23, hub-Run initiative workflow): a `workdir`
        `git.push` row's default-branch refusal "reads the SUBMODULE's default branch, not the
        Run Repository's". `symbolic-ref`, not another `ls-remote`: a plain clone — which is
        what `submodule_update`'s `git submodule update --init` makes for every new submodule —
        already records the remote's `HEAD` locally, so this reads a fact the checkout already
        established rather than asking the remote a second time.

        `None` covers both absences the caller cannot tell apart and does not need to:
        `workdir` is not an initialized submodule (`_submodule_dir`'s own answer), or the
        local record of `origin/HEAD` was never made.
        """
        submodule = _submodule_dir(self._attempt, worktree, workdir)
        if submodule is None:
            return None
        ref = self._attempt("-C", str(submodule), "symbolic-ref", "-q", ORIGIN_HEAD)
        if ref is None:
            return None
        name = ref.strip()
        if not name.startswith(ORIGIN_HEAD_NAMESPACE):
            return None
        return name[len(ORIGIN_HEAD_NAMESPACE) :]

    def _commit_workdir(self: _Runner, worktree: Path, message: str, workdir: str) -> str | None:
        """`WorktreeCommands.commit`'s `workdir` half (AD-9; H2) — split here for the 400-line
        cap and because `_submodule_dir`, the resolution both this and `_push_workdir` need,
        already lives beside `submodule_checkout`. Stage everything in the submodule, then
        commit; nothing staged answers with the sha already at `HEAD` rather than letting
        `git commit` fail on an empty index — the same "nothing changed is not a failure" the
        worktree-root commit-guard reads from `git status` before ever calling this.
        """
        submodule = _submodule_dir(self._attempt, worktree, workdir)
        if submodule is None:
            return None
        self._run("-C", str(submodule), "add", EVERYTHING)
        dirty = self._run(
            "-C", str(submodule), *RAW_PATHS, "status", "--porcelain", UNTRACKED_ALL
        ).strip()
        if not dirty:
            head = self._attempt("-C", str(submodule), "rev-parse", "--verify", "--quiet", "HEAD")
            return head.strip() if head else ""
        self._run("-C", str(submodule), *NO_HOOKS, *AUTHOR, "commit", "--message", message)
        return self._run("-C", str(submodule), "rev-parse", "HEAD").strip()

    def _push_workdir(
        self: _Runner, worktree: Path, branch: str, set_upstream: bool, workdir: str
    ) -> str | None:
        """`WorktreeCommands.push`'s `workdir` half (AD-14; H2) — the submodule's own origin,
        never the Run Repository's; `None` is `_submodule_dir`'s own "not a submodule"."""
        submodule = _submodule_dir(self._attempt, worktree, workdir)
        if submodule is None:
            return None
        upstream = ("--set-upstream",) if set_upstream else ()
        return self._run("-C", str(submodule), "push", *upstream, ORIGIN, END_OF_OPTIONS, branch)

    def _gitlink_paths(self: _Runner, worktree: Path) -> tuple[str, ...]:
        """Every path this tree's index records as a gitlink — a submodule pointer, not
        content. `WorktreeCommands.stage` calls this through the `_Runner` protocol (the
        400-line cap left the room for it here, beside the mode constant it reads).

        `ls-files -s`, not `submodule status`: the index carries the gitlink mode (`160000`)
        for every submodule the tree names, whether or not it was ever initialized, and
        `stage` needs exactly that fact rather than which ones currently have a checkout. `-z`
        for the reason every other listing in this adapter uses it — a non-ASCII path is never
        quoted, so the exclusion pathspec built from this answer matches the path `ls-files`
        named.
        """
        listing = self._attempt("-C", str(worktree), "ls-files", "-s", "-z")
        paths: list[str] = []
        for entry in (listing or "").split(NUL):
            if not entry:
                continue
            mode, _, rest = entry.partition(" ")
            if mode == GITLINK_MODE:
                _, _, path = rest.partition("\t")
                if path:
                    paths.append(path)
        return tuple(paths)


def _submodule_dir(attempt: _Attempt, worktree: Path, workdir: str) -> Path | None:
    """The folder `workdir` names, or `None` when it is not an initialized submodule.

    The pathspec is not trusted to be a submodule by itself: `git submodule status -- repos`
    answers happily for a submodule *under* `repos`, and running a step in `repos` because of
    that would be the silent fall back to a wrong tree AD-9 forbids. So the listed path is
    compared with the asked-for one, normalised the one way a Template's value can differ
    harmlessly (`./repos/member`, `repos/member/`).
    """
    wanted = _normalised(workdir)
    for path in _initialized(attempt, worktree, recursive=False, pathspec=workdir):
        if _normalised(path) == wanted:
            return worktree / path
    return None


def _initialized(
    attempt: _Attempt, worktree: Path, *, recursive: bool, pathspec: str | None = None
) -> list[str]:
    """Every submodule path `git submodule status` reports as initialized, in git's order.

    `_attempt`, because a pathspec the tree does not hold at all is a non-zero exit and the
    port's second convention makes that "not there" rather than a failure — the same answer
    a path that is simply not a submodule gives, since it is the same stop for the Operator.
    `core.quotePath=false` for the reason `worktrees.py::status` carries it: a quoted
    non-ASCII path is a different string from the one the caller asked about.
    """
    arguments = ["-C", str(worktree), *RAW_PATHS, "submodule", "status"]
    if recursive:
        arguments.append("--recursive")
    if pathspec is not None:
        arguments += [END_OF_OPTIONS, pathspec]
    listing = attempt(*arguments)
    return [path for flag, path in _status_lines(listing or "") if flag != UNINITIALIZED]


def _status_lines(listing: str) -> list[tuple[str, str]]:
    """`{flag}{sha} {path} ({describe})` → `(flag, path)`, for each line git wrote.

    Parsed by position rather than by regular expression: the flag is column 1, the object
    name is the first field after it whatever its width (so a SHA-256 repository parses too),
    and the path is the rest with git's optional `describe` suffix taken off the end.
    """
    parsed: list[tuple[str, str]] = []
    for line in listing.splitlines():
        if not line.strip():
            continue
        _, _, tail = line[1:].partition(" ")
        if tail.endswith(DESCRIBE_CLOSER) and DESCRIBE_OPENER in tail:
            tail = tail.rsplit(DESCRIBE_OPENER, 1)[0]
        if tail:
            parsed.append((line[0], tail))
    return parsed


def _normalised(path: str) -> str:
    """One spelling of a repository-relative path, so `./a/b`, `a/b/` and `a/b` are one."""
    return str(PurePosixPath(path.strip()))


def _local_branch(attempt: _Attempt, submodule: Path, branch: str) -> str | None:
    """The submodule's own branch of that name, or `None` when it has none yet."""
    answer = attempt(
        "-C", str(submodule), "rev-parse", "--verify", "--quiet", f"{HEADS_NAMESPACE}{branch}"
    )
    return answer.strip() if answer else None


def _remote_head(attempt: _Attempt, submodule: Path, branch: str | None) -> str | None:
    """`origin/{branch}` when the member's remote holds it after the fetch, else `None`.

    `None` in for `None` out, which is what makes the three-way start point of
    `submodule_checkout` one expression: a `base` the Template did not declare and one the
    member repository does not hold are the same absence, and AD-14 gives both the same
    answer — the submodule's current HEAD.
    """
    if branch is None:
        return None
    remote = f"{ORIGIN}/{branch}"
    found = attempt("-C", str(submodule), "rev-parse", "--verify", "--quiet", remote)
    return remote if found else None
