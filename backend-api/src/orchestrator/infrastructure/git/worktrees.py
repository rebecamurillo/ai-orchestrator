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

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from orchestrator.domain.ports.git import NO_UPSTREAM, Change, ChangeKind, GitError, NoUpstream

#: Where a base clone's origin refs live. The same word `subprocess_git.py` uses.
ORIGIN = "origin"

#: The namespace a branch lives in on a remote — the same constant `subprocess_git.py`
#: compares `ls-remote` answers against, and `submodules.py` imports for its own remote
#: branch checks.
HEADS_NAMESPACE = "refs/heads/"

#: The two config values every writing command carries: see the module docstring.
NO_HOOKS = ("-c", "core.hooksPath=/dev/null")
AUTHOR = ("-c", "user.name=orchestrator", "-c", "user.email=orchestrator@local")

#: Ends git's option parsing, before a branch name or a pathspec the Operator's data decided.
END_OF_OPTIONS = "--"

#: What `-z` separates paths with, so a non-ASCII path never has to be unquoted to be used.
NUL = "\0"

#: Everything a `stage` stages when the caller named no pathspec.
EVERYTHING = "-A"

#: What `status` asks for, and both are AD-17's doing. Porcelain collapses a wholly untracked
#: *directory* to one `?? dir/` entry, so an `AGENTS.md` an agent created inside a folder it
#: also created would never be named and the frozen-anchor rule could not see it;
#: `--untracked-files=all` enumerates the files themselves. And porcelain C-quotes any path
#: holding non-ASCII or special bytes (`"sp\303\251cs/SPEC.md"`), which is a *different
#: string* from the one the anchor set and the `AGENTS.md` basename are compared against —
#: `core.quotePath=false` prints the bytes, the same reason `-z` is used everywhere else here.
#: A third `status` option, so it sits beside those two *after* the subcommand and never in
#: the `-c` prefix, and asked for only by the reuse-when-clean check: `=all` drops both a
#: gitlink the hub's index and the submodule's HEAD disagree about and whatever the
#: submodule's own tree is doing, which is the *worktree's own* cleanliness AD-14 means where
#: a Run advances its members on purpose (H7, 2026-09-24).
UNTRACKED_ALL = "--untracked-files=all"
RAW_PATHS = ("-c", "core.quotePath=false")
IGNORE_SUBMODULES = "--ignore-submodules=all"

#: `--name-status` letters this system distinguishes; anything else — `M`, `T`, `U` — is a
#: modification, which is what AD-17 needs to know about a path that was already there.
STATUS_KINDS: dict[str, ChangeKind] = {"A": "added", "D": "deleted"}

#: The two letters that carry a second path: git writes `R100 old new`, and AD-17 reads that
#: as the old path gone and the new one created.
TWO_PATH_STATUSES = "RC"

#: Excludes one path from an `add -A` pathspec, in git's own pathspec-magic spelling.
EXCLUDE_PATHSPEC = ":!{path}"

#: What a merge this system made says it is. The branch, not the run: an Operator reading
#: the integration branch's history wants to know which epic landed, and `git.merge` merges
#: exactly one (AD-9, spine "Shipped kinds").
MERGE_MESSAGE = "merge {branch} (orchestrator)"

#: What `--diff-filter=U` answers with, and the heading the listing is put under so a
#: reader of the park can tell git's own words from the index's.
UNMERGED = "U"
CONFLICTED_HEADING = "conflicted paths:"


#: `SubprocessGit._attempt`, as `_with_conflicts` below needs to see it: a command whose
#: non-zero exit means "nothing there" rather than "broken".
_Attempt = Callable[..., "str | None"]


def _origin_holds(attempt: _Attempt, worktree: Path, branch: str) -> bool:
    """Whether the origin has a head named `branch`."""
    held = attempt("-C", str(worktree), "ls-remote", "--heads", ORIGIN, END_OF_OPTIONS, branch)
    return bool((held or "").strip())


class _Runner(Protocol):
    """The helpers `SubprocessGit` already has, as this mixin needs to see them.

    `_commit_workdir`/`_push_workdir`/`_gitlink_paths` are `SubmoduleCommands`'s (H2), moved
    there for the 400-line cap and because the resolution `workdir` and gitlink exclusion both
    need lives beside `submodule_checkout`. Declared here rather than imported: `submodules.py`
    already imports *from* this module, and the reverse would cycle. `SubprocessGit` mixes
    both classes into one `self`, so the methods are there at run time regardless.
    """

    def _run(self, *arguments: str) -> str: ...

    def _attempt(self, *arguments: str) -> str | None: ...

    def _remote(self, branch: str) -> str: ...

    def _commit_workdir(self, worktree: Path, message: str, workdir: str) -> str | None: ...

    def _push_workdir(
        self, worktree: Path, branch: str, set_upstream: bool, workdir: str
    ) -> str | None: ...

    def _gitlink_paths(self, worktree: Path) -> tuple[str, ...]: ...


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
        so a Run whose working branch *is* the default branch would fail on its checkout row.
        Idempotent: a `HEAD` that is already detached is written back unchanged.
        """
        head = self._attempt("-C", str(base), "rev-parse", "--verify", "--quiet", "HEAD")
        if head is not None:
            self._run("-C", str(base), "update-ref", "--no-deref", "HEAD", head.strip())
        path.parent.mkdir(parents=True, exist_ok=True)
        arguments = ("-C", str(base), *NO_HOOKS, "worktree", "add")
        if start_point is None:
            return self._run(*arguments, str(path), END_OF_OPTIONS, branch)
        return self._run(*arguments, "-b", branch, str(path), END_OF_OPTIONS, start_point)

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
        if not _origin_holds(self._attempt, worktree, branch):
            return None
        fetched = self._run("-C", str(worktree), "fetch", ORIGIN, END_OF_OPTIONS, branch)
        merged = self._run("-C", str(worktree), *NO_HOOKS, "merge", "--ff-only", "FETCH_HEAD")
        return fetched + merged

    def merge(self: _Runner, worktree: Path, branch: str) -> str | NoUpstream | None:
        """Abort any merge in progress, fetch, and merge `origin/{branch}` with `--no-ff`.

        **A branch the origin does not hold is `NO_UPSTREAM`, decided before the fetch** —
        the fetch would fail on it, and a fresh initiative branch has no origin ref until its
        first push. The question is `sync`'s own (`ls-remote --heads`).

        **The abort is guarded by a probe, not by ignoring a failure.** `git merge --abort`
        exits 128 when there is no merge to abort, so it cannot be run unconditionally;
        `rev-parse --verify --quiet MERGE_HEAD` is the question it answers to. Not
        `.git/MERGE_HEAD`: every tree this system merges in is a *linked* worktree, whose
        `.git` is a file and whose `MERGE_HEAD` lives in the base clone's
        `worktrees/{name}/` directory — the filesystem check would look in the wrong place
        for every Run there is, and would quietly answer "no merge in progress" every time.

        **The ancestor test decides `None` before anything is written.** A ref the branch
        already holds is AD-13's `done · already merged`, and asking `merge-base
        --is-ancestor` is how that stays a fact about the history rather than a guess from
        git's "Already up to date" wording.

        **A conflict is raised with the conflicted files appended.** git's own message names
        them, but only for the paths it printed a `CONFLICT` line for; `--diff-filter=U` is
        the index's own answer and it is what the Operator's stop shows. The conflicted
        merge is left in place on purpose — the abort above is the next call's business.
        """
        if self._attempt("-C", str(worktree), "rev-parse", "--verify", "--quiet", "MERGE_HEAD"):
            self._run("-C", str(worktree), *NO_HOOKS, "merge", "--abort")
        if not _origin_holds(self._attempt, worktree, branch):
            return NO_UPSTREAM
        self._run("-C", str(worktree), "fetch", ORIGIN, END_OF_OPTIONS, branch)
        remote = f"{ORIGIN}/{branch}"
        contained = self._attempt(
            "-C", str(worktree), "merge-base", "--is-ancestor", remote, "HEAD"
        )
        if contained is not None:
            return None
        try:
            self._run(
                "-C",
                str(worktree),
                *NO_HOOKS,
                *AUTHOR,
                "merge",
                "--no-ff",
                "--message",
                MERGE_MESSAGE.format(branch=branch),
                END_OF_OPTIONS,
                remote,
            )
        except GitError as error:
            raise _with_conflicts(self._attempt, worktree, error) from error
        return self._run("-C", str(worktree), "rev-parse", "HEAD").strip()

    def status(self: _Runner, worktree: Path, *, ignore_submodules: bool = False) -> str:
        """`git status --porcelain`: the empty string when the worktree is clean.

        Every untracked file by name and every path unquoted — see `UNTRACKED_ALL` and
        `RAW_PATHS` above for why AD-17 needs both. The return type is unchanged: one string,
        one line per path, which is what `git_commit.py` and `rules/protected_paths.py` read.
        `ignore_submodules` adds the third option, so a hub worktree whose members a Run
        advanced on purpose reports its own tree and nothing else (AD-14, H7); every other
        caller passes nothing and gets the exact command it always got.
        """
        ignore = (IGNORE_SUBMODULES,) if ignore_submodules else ()
        arguments = ("-C", str(worktree), *RAW_PATHS, "status", "--porcelain", UNTRACKED_ALL)
        return self._run(*arguments, *ignore)

    def stage(self: _Runner, worktree: Path, pathspec: str | None = None) -> None:
        """`git add -A`, over everything or over one pathspec the caller named.

        An "everything" stage excludes every gitlink the index already records, so the hub
        Run never commits a submodule pointer move (AD-14, ratified 2026-09-23) — true even
        of a submodule never materialised, since the index carries the gitlink whether or not
        it is initialized. A repository with no submodules records none, so this is the exact
        command it always was there. A named pathspec (the commit-guard's own spec-folder
        stage) is trusted as it is: it cannot itself denote a submodule.
        """
        arguments = ("-C", str(worktree), "add", EVERYTHING)
        if pathspec is None:
            exclude = tuple(
                EXCLUDE_PATHSPEC.format(path=path) for path in self._gitlink_paths(worktree)
            )
            if exclude:
                self._run(*arguments, END_OF_OPTIONS, ".", *exclude)
                return
            self._run(*arguments)
            return
        self._run(*arguments, END_OF_OPTIONS, pathspec)

    def commit(
        self: _Runner, worktree: Path, message: str, workdir: str | None = None
    ) -> str | None:
        """Commit what is staged as the orchestrator, and answer with the new commit.

        Without `workdir`, exactly what this always was: the caller staged, and this commits.
        With it (AD-9, ratified 2026-09-23), staging cannot be split from committing across a
        submodule's own tree the way it can at the worktree root, so `_commit_workdir` does
        both over the submodule `workdir` resolves to. `None` is `workdir` not an initialized
        submodule, the same absence `submodule_checkout` and `push` give.
        """
        if workdir is not None:
            return self._commit_workdir(worktree, message, workdir)
        self._run("-C", str(worktree), *NO_HOOKS, *AUTHOR, "commit", "--message", message)
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

    def diff_changes(
        self: _Runner, worktree: Path, from_sha: str, to_sha: str
    ) -> tuple[Change, ...]:
        """`git diff --name-status -z {from} {to}` — a bounded range, with each path's kind.

        `-z` for the reason `diff_names` uses it, and it changes the parsing: with `-z` git
        writes the status and each path as separate NUL-terminated fields rather than as one
        tab-separated line, so a rename arrives as three fields and everything else as two.
        A ref the repository does not hold is `_attempt`'s `None`, which is `()` here.
        """
        raw = self._attempt(
            "-C", str(worktree), "diff", "--name-status", "-z", from_sha, to_sha, END_OF_OPTIONS
        )
        fields = [field for field in (raw or "").split(NUL) if field]
        changes: list[Change] = []
        index = 0
        while index + 1 < len(fields):
            letter = fields[index][:1]
            if letter in TWO_PATH_STATUSES and index + 2 < len(fields):
                changes.append(Change(path=fields[index + 1], kind="deleted"))
                changes.append(Change(path=fields[index + 2], kind="added"))
                index += 3
                continue
            changes.append(
                Change(path=fields[index + 1], kind=STATUS_KINDS.get(letter, "modified"))
            )
            index += 2
        return tuple(changes)

    def diff(self: _Runner, worktree: Path, from_sha: str, path: str) -> str:
        """`git diff {from_sha} -- {path}` — the unified diff of one path against the tree.

        `END_OF_OPTIONS` before the path for the reason every other command here has it: the
        pathspec comes from a stored hit list, and a file whose name begins with a dash must
        not become a flag. `_attempt`, so a ref this worktree does not hold answers `""`
        rather than failing the read (the port's second convention).
        """
        return self._attempt("-C", str(worktree), "diff", from_sha, END_OF_OPTIONS, path) or ""

    def push(
        self: _Runner, worktree: Path, branch: str, set_upstream: bool, workdir: str | None = None
    ) -> str | None:
        """`git push origin {branch}`, with `-u` when this Run created the branch. Never forced.

        With `workdir` (AD-14, ratified 2026-09-23), `_push_workdir` pushes the submodule
        `workdir` resolves to, on its own origin — never the Run Repository's. `None` is the
        same absence `commit` and `submodule_checkout` give.
        """
        if workdir is not None:
            return self._push_workdir(worktree, branch, set_upstream, workdir)
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


def _with_conflicts(attempt: _Attempt, worktree: Path, error: GitError) -> GitError:
    """The same failure, with the index's own unmerged paths appended to git's message.

    A function taking the runner's `_attempt` rather than a method, because it is about
    *reporting* a failure rather than about a git command the port names. `_attempt`, so a
    merge that failed for some reason other than a conflict — nothing unmerged in the index
    — leaves the error exactly as it was rather than swallowing it into a second failure.
    """
    listing = attempt("-C", str(worktree), "diff", "--name-only", f"--diff-filter={UNMERGED}", "-z")
    paths = [path for path in (listing or "").split(NUL) if path]
    if not paths:
        return error
    joined = "\n".join(paths)
    return GitError(
        command=error.command,
        exit_code=error.exit_code,
        output=f"{error.output}\n{CONFLICTED_HEADING}\n{joined}",
    )
