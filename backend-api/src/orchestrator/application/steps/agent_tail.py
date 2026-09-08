"""The `agent` kind's **Story-file contract**: finding the file, keeping it unambiguous, and
routing on it (AD-9, AD-13, FR-16, FR-17).

Split out of `steps/agent.py` because that module is at its 400-line cap and because this is
one subject: `story_files` asks the row's liveness glob, `archive_ambiguous` repairs an
answer that named more than one file, and `tail` routes on the one that is left. The
dependency runs one way — `agent.py` imports this module, never the reverse — so what both
need (`resolved_text`, `committed`, and the three questions about which re-dispatch this is)
lives one layer down, in `context.py`. `archive_ambiguous` is the one function here the
*prepare* phase calls; it is here rather than in `agent.py` because it is the same glob and
the same ambiguity rule the routing below refuses to guess at.

**The order inside `tail` is AD-9's tail order, and it is the module's whole shape:**

1. the protected-path check (5.6), *before* the routing — FR-31 says a modified anchor wins
   over every route, which it cannot do from behind one;
2. the routing (this story), which is `rules/routing.py` and nothing else: this module reads
   the glob and the file and hands the rule plain values;
3. the attempt's spend and the budget check (5.7), *after* the routing — FR-17 says the step
   keeps the status its file routed to and the Run parks on top of it.

Two of the three are seams here, named where they go and doing nothing yet.

**`done` still means "observed".** The row's gate is `liveness` and this module never
changes it: a Story step is green only when the `verify` row after it says so (NFR-2). A row
that declared no `expect` contract at all has nothing to evaluate and reports exactly what it
observed — the shipped Templates all declare one (`application/templates/agent_row.py` writes
`expect` onto every planned `agent` row), so that is a row from outside the dev loop, not a
Story that escaped its contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from orchestrator.application.rules.routing import route
from orchestrator.application.steps.context import (
    StepContext,
    committed,
    operator_retry,
    require_cwd,
    require_workspace,
    resolved_text,
    retrying,
)
from orchestrator.application.story_file import StoryFile, parse
from orchestrator.application.templates.agent_row import (
    EXPECT_KEY,
    RETRY_KEY,
    SPEC_CHECKPOINT_KEY,
    SPEC_FOLDER_KEY,
    STORY_ID_KEY,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.values import Park, Retry, StepResult

#: The sub-keys of the two contracts, as `application/templates/agent_row.py:52-54` writes
#: them onto the row. `Retry`'s own field names, so the three below name one thing each.
EXPECT_FILES = "files"
RETRY_MAX = "max"
RETRY_PROMPT = "prompt"
RETRY_RESUME_SESSION = "resume_session"

#: The liveness glob FR-16 names, for a row whose `expect` declared none of its own.
STORY_FILE_GLOB = "{spec_folder}/stories/{story_id}-*.md"

#: Where AD-13's de-ambiguation puts every match it is not keeping — the same folder FR-18's
#: Answer archives a blocked Story file to — and how many matches make an ambiguity.
ANSWERS_DIRECTORY = "{spec_folder}/stories/.answers"
AMBIGUOUS = 2

#: What a dispatch that ran past its deadline leaves. Not an exit code and not a route: the
#: harness never got to write a file, so there is nothing for FR-16 to read.
TIMED_OUT = "timeout {path} after {n} min"


def finish(
    ctx: StepContext, attempt: Attempt, result: HarnessResult, timeout_min: float
) -> StepResult:
    """Record what the harness did, then say what the row reached; `mark_finished` runs
    first, so a killed attempt is as fully recorded as one that exited cleanly (AD-8)."""
    finished = attempt.model_copy(
        update={
            "ended_at": ctx.ports.clock.now(),
            "end_sha": ctx.ports.git.head_sha(require_cwd(ctx)),
            "exit_code": result.exit_code,
            "session_id": result.session_id,
            "log_path": str(result.log_path),
            **usage(result),
        }
    )
    committed(ctx, lambda attempts: attempts.mark_finished(finished))
    if result.timed_out:
        reason = TIMED_OUT.format(path=ctx.row.path, n=timeout_min)
        return StepResult(
            status="error",
            gate=ctx.row.gate,
            output_ref=str(result.log_path),
            reason=reason,
            park=Park(kind="timeout", reason=reason, path=ctx.row.path),
        )
    return tail(ctx, finished, result)


def tail(ctx: StepContext, attempt: Attempt, result: HarnessResult) -> StepResult:
    """What the dispatch reached, by the Story file it wrote and nothing else (FR-16).

    `attempt` is the finished record, and the two seams marked below are its only readers
    here: the protected-path check compares the agent's range against `attempt.start_sha`,
    and the budget check reads the same attempt's usage and spend.
    """
    log = str(result.log_path)
    # 5.6 — the protected-path check goes here, before the routing. FR-31: a modified
    # anchor wins over every route below, which it cannot do from behind one.
    files = story_files(ctx)
    if files is None:
        return StepResult(status="done", gate=ctx.row.gate, output_ref=log)
    routed = route(
        _parsed(ctx, files),
        files,
        result.exit_code,
        bool(ctx.with_resolved.get(SPEC_CHECKPOINT_KEY)),
        ctx.row.retry_count,
        retry_of(ctx),
        gate=ctx.row.gate,
        path=ctx.row.path,
    )
    # 5.7 — the attempt's spend and the budget check go here, after the routing. FR-17: the
    # step keeps the status its file routed to and the Run parks on top of it.
    return routed.model_copy(update={"output_ref": log})


def story_files(ctx: StepContext) -> tuple[str, ...] | None:
    """Every path the row's liveness glob matches, or `None` when it declared no contract.

    Sorted and de-duplicated, so "which files matched" is one answer whatever order the
    filesystem hands them back in and however many globs the Template wrote.
    """
    expect = ctx.with_resolved.get(EXPECT_KEY)
    if not isinstance(expect, Mapping):
        return None
    workspace = require_workspace(ctx, ctx.cwd)
    found: set[str] = set()
    for pattern in _globs(ctx, expect):
        found.update(workspace.glob(pattern))
    return tuple(sorted(found))


def archive_ambiguous(ctx: StepContext) -> tuple[str, ...]:
    """AD-13: a re-run after `ambiguous story file` keeps the newest match and archives the
    rest, so the ambiguity cannot compound over attempts.

    Both kinds of re-run are covered. The Operator's *Retry* is the one that matters:
    `ambiguous story file` is a `misconfigured` stop, and AD-9 never re-executes one of
    those automatically, so a person choosing Retry is the only way that row runs again.
    The Template's own `retry` is covered too — it can only ever have seen one file, so
    this returns immediately, and the hook stays right if the routing ever changes.

    Newest is by mtime and then by name, so the choice is never a coin toss. **Both ends of
    every rename are reported**: `agent.py` stages them into the prepare commit, so the move
    is the orchestrator's own recorded write and `start_sha` is read off a clean tree —
    without that, 5.6's `diff_names(start_sha, end_sha)` would attribute this rename to the
    agent, which AD-17 and FR-31 forbid.
    """
    if not (operator_retry(ctx) or retrying(ctx)):
        return ()
    matches = story_files(ctx) or ()
    if len(matches) < AMBIGUOUS:
        return ()
    workspace = require_workspace(ctx, ctx.cwd)
    answers = ANSWERS_DIRECTORY.format(
        spec_folder=resolved_text(ctx.with_resolved, SPEC_FOLDER_KEY)
    )
    newest = max(matches, key=lambda path: (workspace.mtime(path), path))
    moved: list[str] = []
    for path in (match for match in matches if match != newest):
        archived = f"{answers}/{PurePosixPath(path).name}"
        workspace.move(path, archived)
        moved += [path, archived]
    return tuple(moved)


def retry_of(ctx: StepContext) -> Retry | None:
    """The `retry` contract the planner flattened onto this row, or `None` for a row
    that declared none — or one whose `max` or `prompt` the Template left unset, which is
    a contract that could not be applied rather than one that fires with an empty prompt."""
    declared = ctx.with_resolved.get(RETRY_KEY)
    if not isinstance(declared, Mapping):
        return None
    prompt, most = declared.get(RETRY_PROMPT), declared.get(RETRY_MAX)
    if not isinstance(prompt, str) or not isinstance(most, int):
        return None
    return Retry(
        prompt=prompt, max=most, resume_session=bool(declared.get(RETRY_RESUME_SESSION, True))
    )


def usage(result: HarnessResult) -> dict[str, Any]:
    """The harness's figures, or nothing — never zeroes read back as measured (AD-11)."""
    figures = result.usage
    if figures is None:
        return {}
    return {
        "tokens_in": figures.tokens_in,
        "tokens_out": figures.tokens_out,
        "cost_usd": figures.cost_usd,
        "cost_provisional": True,
    }


def _parsed(ctx: StepContext, files: tuple[str, ...]) -> StoryFile | None:
    """The one match, read and parsed — or `None`, which liveness reports rather than routes.

    A file that vanished between the glob and the read is `""`, which parses to `None`: the
    same answer as one whose frontmatter is unreadable, and the same stop.
    """
    if len(files) != 1:
        return None
    return parse(files[0], require_workspace(ctx, ctx.cwd).read(files[0]) or "")


def _globs(ctx: StepContext, expect: Mapping[str, Any]) -> tuple[str, ...]:
    """`expect.files` as the planner resolved it (AD-7), or FR-16's own glob for a row
    whose Template declared no `files` at all."""
    declared = tuple(str(pattern) for pattern in expect.get(EXPECT_FILES) or ())
    return declared or (
        STORY_FILE_GLOB.format(
            spec_folder=resolved_text(ctx.with_resolved, SPEC_FOLDER_KEY),
            story_id=resolved_text(ctx.with_resolved, STORY_ID_KEY),
        ),
    )
