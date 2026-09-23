"""The `agent` kind's `workdir`: one attempt, two trees, both checked (AD-9, AD-17).

Split out of `steps/agent.py` at the 400-line cap, the way `agent_tail.py` and
`agent_prompt.py` were. Everything that has to answer *which tree* lives here, so `agent.py`
keeps AD-9's side-effect order as its shape and reads a tree rather than deciding one.

**What `workdir` moves, and what it deliberately does not.** A row declaring
`with {workdir: repos/member}` dispatches its harness **inside that submodule's checkout** —
the process's `cwd`, and therefore the stall detector's watched folder, is
`{run worktree}/{workdir}` — and every git fact the attempt records is the *submodule's*:
`start_sha`, `end_sha`, the WIP commit, `frozen_test_files`. What does **not** move is
`StepContext.cwd`: the specs live in the hub, so the orchestrator's own writes
(`project-context.md`, the Answer archive, the `## Verify Failure` append, the prepare
commit) and every `Workspace` read — `expect.files`, the Story-file glob, `prompt_file` —
stay rooted at the run worktree root, exactly as on a row that declares no `workdir`.

**The spec-path contract, which H3's templates encode** (stated here because a Template
author cannot read it off anything else): a `workdir` dispatch is handed the spec folder as
an **absolute** path — `{run worktree root}/{spec_folder}` — inside the prompt, and nothing
else in the row changes spelling. The agent's `cwd` is the member checkout, so a
root-relative `specs/…` in the prompt would make it write the Story file into the member
repository; the absolute path is what keeps the Story file landing in the hub, where
`expect.files` (checked through a `Workspace` rooted at the run root, hence **run-root
relative**) and the Story-file glob look for it. The prerendered workflow path needs no rule
of its own: `render_skill.py` resolves its `--project-root` and prints an absolute path.

Two things stay at the root on purpose and are not oversights. **Orphan control** kills the
process group and then waits out git's own `.git/index.lock` in the run worktree: a submodule
of a linked worktree keeps its git directory under the base clone, so there is no
`{workdir}/.git/` for a `Workspace` to look in, and the lock that would actually block this
row's next write is the hub's. **The prerendered workflow** is rendered with `--project-root`
at the hub, where `bmad.install` puts `_bmad/`; it prints an absolute path, so a prompt read
from the member checkout still resolves it.

**AD-17, amended (ratified 2026-09-23).** One attempt spans two trees:

- the **workdir tree** carries `start_sha`/`end_sha`, and `repository.test_globs` are matched
  against *workdir-relative* paths, so a member repository's own `tests/**` is what the frame
  freezes;
- the **worktree root** carries `root_start_sha`/`root_end_sha` — the hub's HEAD at the same
  two moments — so the hub's anchors are still checked over agent ranges only.

**One spelling, one flat list.** Every hit, from either tree, is reported **run-worktree
relative**: a workdir hit is prefixed `{workdir}/`. That is what keeps `run.accepted_paths` a
single flat list whose entries are unambiguous, keeps the reason sentence readable in a Run
whose rows work in several member repositories, and lets one `rules/protected_paths.check`
call cover both trees — the frame's anchor set already holds both trees' frozen tests, for
the same reason and in the same spelling (`frozen_test_files` below).

**The gitlink pointer is never a hit.** A commit inside the submodule moves the hub's
`{workdir}` gitlink, and a dirty submodule shows as ` M {workdir}` in the hub's status; the
root half therefore drops every change at or under `{workdir}` before checking. Those files
are not lost — they are exactly what the workdir half reports, under the same names. (This is
the *check's* exclusion; `Git.stage`'s own gitlink exclusion is the adapter's and separate.)

**What this story does not cover.** A row that declares no `workdir` is byte-for-byte
unchanged, so a *hub* agent (or a `workdir` agent reaching into a **different** submodule)
that edits a file inside a submodule is still seen only as the gitlink the root range
reports. AD-17's amendment names the mechanism for it — read `Git.status` of each initialized
submodule and report submodule-relative paths — and the spelling above is already the one it
would use; what it costs is enumerating the initialized submodules on every agent attempt of
every Run, which is a behaviour change to the non-workdir path this story is scoped to leave
alone. Whenever it is built, that enumeration is a **read** (`Git.submodule_path`'s own
listing, never `submodule_update`): H6 is what it costs to confuse the two.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

from orchestrator.application.rules.protected_paths import uncommitted
from orchestrator.application.steps import WORKDIR_KEY
from orchestrator.application.steps.context import (
    StepContext,
    require_cwd,
    require_env,
    resolved_text,
)
from orchestrator.application.templates.agent_row import SPEC_FOLDER_KEY, STORY_ID_KEY
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ports.git import Change
from orchestrator.domain.values import Park, StepResult

#: AD-9's own sentence for a `workdir` that is not a workdir — the same words
#: `git.submodule`, `git.commit` and `git.push` park with, because it is the same stop.
NOT_A_SUBMODULE = "workdir {path} is not an initialized submodule"

#: The WIP commit this row places in whichever tree it works in (AD-9). Named here because
#: the tree it lands in is this module's question; `steps/agent.py` re-exports it.
WIP_MESSAGE = "wip: story {id} attempt {n} (interrupted)"

#: Every path at a ref, as a pathspec. Not `""`: git refuses that by name and the adapter
#: reports a refusal as `()`, so AD-17's set would come back empty and nothing would fail.
WHOLE_TREE = "."

#: How a workdir-relative path is spelled once it leaves this module — see "One spelling".
QUALIFIED = "{workdir}/{path}"


def declared(ctx: StepContext) -> str:
    """The submodule this row runs in, normalised, or `""` for a row that declares none.

    Normalised the one way a Template's value can differ harmlessly (`./repos/member`,
    `repos/member/`), so the prefix a hit carries is one string whichever spelling the
    Template used — the same normalisation `infrastructure/git/submodules.py` applies before
    it compares a workdir with what `git submodule status` listed.
    """
    written = resolved_text(ctx.with_resolved, WORKDIR_KEY)
    return str(PurePosixPath(written)) if written else ""


def tree(ctx: StepContext) -> Path:
    """The tree this row's git bookkeeping happens in: the submodule, or the worktree root.

    Pure: the folder a repository-relative `workdir` names is `{worktree}/{workdir}` and
    nothing has to be asked to know it. That it is an *initialized* submodule is settled once
    per dispatch by `verify` below, before anything is written.
    """
    root = require_cwd(ctx)
    workdir = declared(ctx)
    return root / workdir if workdir else root


def verify(ctx: StepContext) -> StepResult | None:
    """`None` when this row's `workdir` resolves, or the park AD-9 gives when it does not.

    Asked before any commit is placed and before any attempt column is written, for the
    reason the harness lookup is asked first: a row naming a folder this worktree does not
    hold as a submodule must stop without leaving a commit behind.

    `Git.submodule_path` is the probe, and that it **reads only** is the whole of why it
    exists (H6, 2026-09-23). This asked `Git.submodule_update` until H6: idempotent about the
    *recorded* commits, yes — but `git submodule update` in default checkout mode resets the
    submodule to the commit the hub's index holds, and AD-14 has the hub Run never commit a
    gitlink move, so that pointer is frozen at whatever the branch was cut with. The second
    `workdir` dispatch into one submodule within a Run — an epic's `gen-e2e` after its story's
    commit-guard already committed there — therefore detached the member checkout at the stale
    pointer *before writing anything*, and everything it then committed sat on an orphan the
    `git.push` row's branch ref never pointed at. Both rows reported `done`; the work was gone.
    """
    workdir = declared(ctx)
    if not workdir:
        return None
    if ctx.ports.git.submodule_path(require_cwd(ctx), workdir) is not None:
        return None
    reason = NOT_A_SUBMODULE.format(path=resolved_text(ctx.with_resolved, WORKDIR_KEY))
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        reason=reason,
        park=Park(kind="misconfigured", reason=reason, path=ctx.row.path),
    )


def wip_commit(ctx: StepContext) -> None:
    """Commit leftover dirt so this row starts tracked (AD-9), in the tree it works in.

    The workdir form is one call and not two: `Git.commit(..., workdir=…)` stages and commits
    inside the submodule together, because staging cannot be split from committing across two
    trees (the port's own words, H2).
    """
    if ctx.previous_attempt is None:
        return
    git, root = ctx.ports.git, require_cwd(ctx)
    if not git.status(tree(ctx)).strip():
        return
    message = WIP_MESSAGE.format(id=resolved_text(ctx.with_resolved, STORY_ID_KEY), n=ctx.attempt.n)
    workdir = declared(ctx)
    if workdir:
        git.commit(root, message, workdir=workdir)
        return
    git.stage(root)
    git.commit(root, message)


def start_shas(ctx: StepContext) -> dict[str, Any]:
    """The start half's git facts (AD-8): both trees' HEADs and the frame's frozen tests.

    A row with no `workdir` writes `root_start_sha: None` — the spine's "written only when
    the row declares `workdir`" — so nothing about a root row's stored range changes.
    """
    git, workdir = ctx.ports.git, declared(ctx)
    start_sha = git.head_sha(tree(ctx))
    root_start_sha = git.head_sha(require_cwd(ctx)) if workdir else None
    return {
        "start_sha": start_sha,
        "root_start_sha": root_start_sha,
        "frozen_test_files": frozen_test_files(ctx, start_sha, root_start_sha),
    }


def end_shas(ctx: StepContext) -> dict[str, Any]:
    """The finish half's, at the moment the harness exited — the same two trees, in order."""
    git = ctx.ports.git
    return {
        "end_sha": git.head_sha(tree(ctx)),
        "root_end_sha": git.head_sha(require_cwd(ctx)) if declared(ctx) else None,
    }


def frozen_test_files(
    ctx: StepContext, start_sha: str | None, root_start_sha: str | None
) -> tuple[str, ...] | None:
    """AD-17's frozen set for this frame, from the committed trees at the start SHAs.

    `None` on every attempt that is not the frame's first — the predecessor-skip this rule
    has always had — and on a tree with no commit in it at all.

    A `workdir` frame freezes **both** trees, in the module's one spelling: the submodule's
    own matches, prefixed `{workdir}/`, and the hub's own matches as they stand. One field
    carries both because the frame's anchor set is built out of it (`walk_frame.py`), and
    AD-17's amendment asks the root half of the check to cover "the hub's own frozen test
    files" while the workdir half covers the member's — two questions, one list of paths,
    each spelled the way its hit will be reported.
    """
    previous = ctx.previous_attempt
    if previous is not None and previous.start_sha is not None:
        return None
    globs = require_env(ctx).test_globs
    workdir = declared(ctx)
    if not workdir:
        if start_sha is None:
            return None
        return tuple(sorted(_matching(ctx, require_cwd(ctx), start_sha, globs)))
    if start_sha is None and root_start_sha is None:
        return None
    found: set[str] = set()
    if start_sha is not None:
        found.update(
            QUALIFIED.format(workdir=workdir, path=path)
            for path in _matching(ctx, tree(ctx), start_sha, globs)
        )
    if root_start_sha is not None:
        found.update(_matching(ctx, require_cwd(ctx), root_start_sha, globs))
    return tuple(sorted(found))


def changes(ctx: StepContext, attempt: Attempt) -> tuple[Change, ...]:
    """Everything this attempt did, across both of its trees, in one spelling (AD-17).

    Each tree contributes its committed range unioned with what it was left holding, so a
    file written and never committed is as much a hit as a committed one; an attempt that
    recorded no range bounded none, and its tree is then the whole of what it did.

    The root half drops the `{workdir}` subtree: the gitlink pointer a submodule commit moved
    is not a file the agent edited, and the files under it are reported by the workdir half
    under the very same names.
    """
    root = require_cwd(ctx)
    workdir = declared(ctx)
    if not workdir:
        return _in(ctx, root, attempt.start_sha, attempt.end_sha)
    inner = _in(ctx, root / workdir, attempt.start_sha, attempt.end_sha)
    hub = _in(ctx, root, attempt.root_start_sha, attempt.root_end_sha)
    return (
        *(
            replace(change, path=QUALIFIED.format(workdir=workdir, path=change.path))
            for change in inner
        ),
        *(change for change in hub if not _inside(workdir, change.path)),
    )


def prompt_scope(ctx: StepContext) -> Mapping[str, Any]:
    """This row's resolved keys as the prompt builder must read them (see "spec-path").

    Unchanged for a row with no `workdir`. For one that has it, the spec folder alone is
    rewritten to its absolute path: the dispatched process stands in the member checkout, and
    every other value on the row is either read by this process through a `Workspace` rooted
    at the run root (`expect.files`, `prompt_file`, `writes`) or is text the Template wrote.
    """
    workdir = declared(ctx)
    spec_folder = resolved_text(ctx.with_resolved, SPEC_FOLDER_KEY)
    if not workdir or not spec_folder:
        return ctx.with_resolved
    return {**ctx.with_resolved, SPEC_FOLDER_KEY: str(require_cwd(ctx) / spec_folder)}


def _in(
    ctx: StepContext, at: Path, start_sha: str | None, end_sha: str | None
) -> tuple[Change, ...]:
    """One tree's agent range plus its uncommitted entries, as one list of changes."""
    git = ctx.ports.git
    ranged: tuple[Change, ...] = ()
    if start_sha is not None and end_sha is not None:
        ranged = git.diff_changes(at, start_sha, end_sha)
    return (*ranged, *uncommitted(git.status(at)))


def _inside(workdir: str, path: str) -> bool:
    """Whether a run-root-relative path is the `{workdir}` gitlink itself or lies under it."""
    return path == workdir or path.startswith(f"{workdir}/")


def _matching(ctx: StepContext, at: Path, ref: str, globs: tuple[str, ...]) -> list[str]:
    """Every path of one tree at one ref that a `repository.test_globs` pattern matches.

    The globs are matched against the paths *that tree* answers with, which is what makes a
    submodule's own `tests/**` the set the frame freezes rather than nothing at all — the
    same pattern would match no path if it were asked about `repos/member/tests/…`.
    """
    listing = ctx.ports.git.list_files(at, ref, WHOLE_TREE)
    return [path for path in listing if any(PurePosixPath(path).full_match(g) for g in globs)]
