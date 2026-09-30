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
from typing import Literal, Protocol, runtime_checkable

#: How one path changed inside a commit range. A rename is neither: the adapter reports it
#: as the pair it is (AD-17 — moving a protected file away is losing it).
ChangeKind = Literal["added", "modified", "deleted"]


@dataclass(frozen=True)
class Change:
    """One path a commit range touched, and how it was touched.

    A value type of the port for the reason `RemoteRef` is one: `diff_names` answers "which
    paths", which is all the commit-guard needs, while AD-17's other call site has to tell a
    deleted anchor from a file the agent created — two facts, so one object rather than two
    parallel tuples the caller could pair up wrongly.
    """

    path: str
    kind: ChangeKind


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

    def list_files(self, dest: Path, ref: str, prefix: str) -> tuple[str, ...]:
        """Every repository-relative path under `prefix` at a ref, in the tree's own order.

        A ref the clone does not hold and a prefix with nothing under it are both `()`, per
        the second convention above: a folder that is not there is an ordinary answer, and
        the planner reads it as "this Story has written no file yet".
        """
        ...

    def worktree_add(self, base: Path, path: Path, branch: str, start_point: str | None) -> str:
        """Add `path` as a worktree of the base clone, and report git's own output.

        `start_point` is what decides which of AD-14's two cases this is. `None` means the
        origin already holds the branch, so the worktree checks it out and tracks
        `origin/{branch}`; a value means the branch does not exist yet and is created at that
        commit-ish. The caller knows which because it asked `branch_exists` first — the port
        does not guess, because guessing wrong is a Run working on the wrong commit.
        """
        ...

    def sync(self, worktree: Path, branch: str) -> str | None:
        """Fetch the branch and fast-forward the worktree onto it; `None` when it has no
        upstream.

        A branch this Run created and never pushed has no upstream, and AD-14 calls that a
        recorded no-op rather than a failure — which is why "not there" is `None` here, like
        everywhere else in this port. A history that cannot be fast-forwarded *is* a failure
        and raises, so that the caller parks the Run on git's own words.
        """
        ...

    def merge(self, worktree: Path, branch: str) -> str | None:
        """Merge `origin/{branch}` into the branch this worktree is on; `None` when that ref
        is already contained.

        AD-14's own words (ratified 2026-09-23): "merge a ref into the current worktree's
        branch, aborting any merge in progress first". Three answers, and each is a fact
        about the two branches rather than a degree of success:

        - **A merge made is its commit.** `--no-ff`, so there is always a new commit and the
          sha is always one the caller has not seen; the `git.merge` kind records it as the
          row's output the way `git.commit` records its own.
        - **A ref already contained is `None`** — the port's second convention applied to
          "nothing to merge", exactly as `sync` applies it to "no upstream". This is also how
          a merge the Operator finished and pushed out of band ends the re-run of the row:
          `done · already merged` (AD-13). A sha-only return could not tell this case from
          the one above without the caller asking `head_sha` twice to re-derive a fact the
          adapter already had.
        - **A conflict is a `GitError`** whose `output` carries git's own message *and* the
          conflicted-file listing, and the conflicted merge is deliberately **left in the
          worktree**: it is what the Operator opens at the `merge_conflict` park. The next
          call is what aborts it, which is what makes AD-13's `retry` — the row re-run whole
          — safe rather than a refusal from a merge that was never concluded.
        """
        ...

    def status(self, worktree: Path, *, ignore_submodules: bool = False) -> str:
        """`git status --porcelain`: the empty string when the worktree is clean.

        **`ignore_submodules` leaves submodule state out of the answer entirely** (AD-14,
        ratified 2026-09-24, hub-Run initiative workflow — H7 defect fix): neither a gitlink
        the index and the submodule's HEAD disagree about, nor the submodule's own tree. It is
        for the one caller judging a **worktree's own** cleanliness where a Run advances the
        submodules on purpose — the `git.worktree` reuse-when-clean check, since the hub Run
        never commits the pointer move `git.submodule` makes, so that divergence is permanent
        and intended rather than dirt. Default `False` for every other caller, unchanged.
        """
        ...

    def stage(self, worktree: Path, pathspec: str | None = None) -> None:
        """Stage everything, or everything under one pathspec.

        Separate from `commit` because the commit-guard stages the spec folder first and the
        rest afterwards (FR-10), and "first" is a fact about two calls rather than about one.
        """
        ...

    def commit(self, worktree: Path, message: str, workdir: str | None = None) -> str | None:
        """Commit whatever is staged as the orchestrator, and answer with the new commit.

        Without `workdir`, exactly what this always was: the caller stages, then calls this,
        and the answer is the new commit.

        **With `workdir`** (AD-9, ratified 2026-09-23, hub-Run initiative workflow), the whole
        thing runs inside that submodule's own repository instead — AD-9's own words are
        "`ctx.cwd` is that folder and the step operates on that folder's own repository" — and
        staging cannot be split from committing across two trees the way it is at the worktree
        root, so this one call does both: everything in the submodule is staged, then
        committed, as the orchestrator. `None` is the one absence with a sentence of its own,
        the same `submodule_checkout` answers: `workdir` does not resolve to an initialized
        submodule, and nothing was written — AD-9's `misconfigured: workdir {path} is not an
        initialized submodule`, never a silent fall back to `worktree`.

        Nothing staged in the submodule is not a failure either: it answers with the sha
        already at the submodule's `HEAD`, exactly as "nothing to commit" is `done` at the
        worktree root and never `git commit`'s own "nothing to commit" failure.
        """
        ...

    def diff_names(self, worktree: Path, from_sha: str) -> tuple[str, ...]:
        """Every path that changed between `from_sha` and the worktree as it stands now."""
        ...

    def diff_changes(self, worktree: Path, from_sha: str, to_sha: str) -> tuple[Change, ...]:
        """Every path two commits differ in, and how each of them changed.

        A **bounded** range, unlike `diff_names`: AD-17 asks what one attempt did between the
        SHA recorded before the harness started and the SHA recorded after it exited, so a
        commit outside those two ends — an operator edit, the orchestrator's own WIP or
        prepare commit — is not in the answer by construction.

        A ref the repository does not hold is `()`, per the second convention above.
        """
        ...

    def diff(self, worktree: Path, from_sha: str, path: str) -> str:
        """The unified diff of **one path** between `from_sha` and the worktree as it stands.

        Text, not a parsed structure: this is what a person reads to judge whether a change
        to a protected file is right (AD-17, FR-31), and every consumer of it renders it
        verbatim. `diff_names`/`diff_changes` answer the machine's question — which paths,
        and how — and are unaffected.

        A path git has nothing to say about is the empty string, per the second convention
        above: a file that did not change between the ref and the tree is an ordinary
        answer, not an error.
        """
        ...

    def push(
        self, worktree: Path, branch: str, set_upstream: bool, workdir: str | None = None
    ) -> str | None:
        """Push the branch to `origin`, setting its upstream when this Run created it.

        Never a force: a rejected push is a `GitError` the caller parks on (AD-13's
        `push_rejected`), and overwriting the remote to make it succeed is the one thing this
        system must not do on someone else's branch.

        **With `workdir`** (AD-14, ratified 2026-09-23, hub-Run initiative workflow), the push
        targets the SUBMODULE's own origin, never the Run Repository's — a member repository
        chooses its own remote, and the hub Run's branch allocation has no say in it. `None` is
        the same absence `commit` and `submodule_checkout` answer: `workdir` does not resolve
        to an initialized submodule, and no command ran. `run.worktrees[]` tracks the Run's own
        worktrees only, so a `workdir` push sets no `pushed` flag anywhere — that bookkeeping
        stays entirely the caller's, outside this port.
        """
        ...

    def submodule_update(self, worktree: Path) -> tuple[str, ...]:
        """Init and update every submodule of the worktree; answer the initialized workdirs.

        AD-14's own words (ratified 2026-09-23, hub-Run initiative workflow): "the init +
        update of the Run's worktree's submodules". This is what turns a hub repository's
        `repos/*` gitlinks into the working folders the rest of the workflow runs in.

        - **The answer is the repository-relative path of every submodule that is now
          initialized**, in git's own order, nested ones included. Two callers need that
          fact for two reasons — the row reports what it materialised, and a `workdir` is
          only a workdir once it appears here — so the adapter reports it rather than making
          each of them ask a second question.
        - **Idempotent.** A worktree whose submodules are already initialized at their
          recorded commits is updated again to the same state, answers the same paths, and
          is not a failure. AD-13's `retry` re-running the row whole is the reason.
        - **It goes through the credential path, because a member repository may be
          private** (AD-5). The clones `git submodule update` spawns are child processes of
          the adapter's own command and inherit the environment `GIT_ASKPASS` lives in.
        - **A worktree with no submodules is `()`**, not an error — the port's second
          convention applied to "there is nothing here to initialize".
        - **It is a write, and its idempotence is about the recorded commits, not about a
          checkout that moved** *(H6 defect fix, 2026-09-23)*. Default checkout mode resets
          every submodule to the commit the **hub's index** records, and nothing advances that
          gitlink, so calling this after a row committed inside a submodule detaches that
          submodule's HEAD at the stale pointer and orphans the commit. Only the
          `git.submodule` update form calls it; anything that merely needs to *know* whether a
          path is an initialized submodule calls `submodule_path` instead.
        """
        ...

    def submodule_path(self, worktree: Path, workdir: str) -> str | None:
        """The initialized submodule `workdir` names, repository-relative — or `None`.

        AD-14's own words (ratified 2026-09-23, hub-Run initiative workflow — H6 defect fix):
        the read-only probe. It **reads and mutates nothing**, which is the whole reason it
        exists beside `submodule_update`: `git submodule update` in its default checkout mode
        resets a submodule to the commit the *hub's* index records, and nothing ever advances
        that gitlink (AD-14: the hub Run never commits gitlink pointer moves). So asking
        `submodule_update` "is this still a submodule?" on every dispatch throws away every
        commit an earlier row of the same Run made inside that submodule, leaving a detached
        HEAD at the stale pointer. This answers the same question and touches no checkout.

        - **The answer is the path git listed, normalised** (`./repos/member`, `repos/member/`
          and `repos/member` are one), so a caller comparing it with a Template's value
          compares one spelling.
        - **`None` is "not an initialized submodule"** — the port's second convention applied
          to the one absence that has a sentence of its own, AD-9's `misconfigured: workdir
          {path} is not an initialized submodule`. A path that is no submodule, one under a
          submodule, and one whose submodule was never initialized are the same answer,
          because they are the same stop.
        """
        ...

    def submodule_checkout(
        self, worktree: Path, workdir: str, branch: str, base: str | None = None
    ) -> str | None:
        """Create or check out `branch` inside the submodule at `workdir`; answer its HEAD.

        AD-14's own words (ratified 2026-09-23, hub-Run initiative workflow):
        "create-or-checkout of `branch` inside the submodule at `workdir` with upstream set,
        cut from `origin/{branch}` when that submodule's remote holds it and from the
        submodule's current HEAD otherwise". `base` is the case in between, which the hub
        workflow needs: an initiative branch neither repository holds yet is cut from the
        member repository's own base branch when its remote holds one.

        Everything happens in the **submodule's own repository** — its remote, its branches,
        its HEAD. The Run's worktree is only how the submodule is located.

        - **`None` is "`workdir` is not an initialized submodule"**: the port's second
          convention applied to the one absence the caller has a sentence for, AD-9's
          `misconfigured: workdir {path} is not an initialized submodule`. A path that is no
          submodule at all and one whose submodule was never initialized are the same
          answer, because they are the same stop, and neither writes anything.
        - **The branch is taken by its exact name, never allocated** (AD-7): it lives in the
          submodule's repository, which the Run's branch allocator cannot reason about.
        - **Upstream is set to `origin/{branch}` even where the remote does not hold it
          yet** — configured for the push that will create it. A branch the remote *does*
          hold is cut from it and tracks it in the ordinary way.
        - **Idempotent.** A submodule already on the branch is fetched and fast-forwarded
          where that is possible and left where it is where it is not; it is never reset to
          a start point, because work an earlier row of the same Run committed inside the
          submodule is exactly what a reset would throw away.
        """
        ...

    def submodule_default_branch(self, worktree: Path, workdir: str) -> str | None:
        """The submodule's own default branch — its remote's `HEAD` — or `None`.

        AD-14's own words (ratified 2026-09-23, hub-Run initiative workflow): a `workdir`
        `git.push` row's refusal of `branch == default_branch` "reads the SUBMODULE's default
        branch, not the Run Repository's" — a member repository's trunk is its own choice, and
        the hub Run has no say in it. Two absences share `None`, as everywhere in this port:
        `workdir` is not an initialized submodule, and a submodule whose remote `HEAD` was
        never recorded locally — "not there" is the honest answer to either rather than a
        guess at which.
        """
        ...

    def head_sha(self, path: Path) -> str | None:
        """The commit `HEAD` points at, or `None` where there is no commit yet."""
        ...

    def remove_worktree(self, base: Path, path: Path) -> None:
        """Remove a worktree of the base clone; a worktree already gone is not a failure."""
        ...

    def delete_branch(self, base: Path, branch: str) -> None:
        """Delete a local branch of the base clone; a branch already gone is not a failure."""
        ...
