"""The `agent` kind's **Story-file contract**: finding the file and routing on it
(AD-9, AD-13, FR-16, FR-17).

Split out of `steps/agent.py` at the 400-line cap. `story_files` asks the row's liveness
glob and `tail` routes on the one file that is left; the archive that repairs ambiguity
lives with the Answer archive in `agent_answer.py`, beside the directory both derive.

**Tail order (AD-9):** (1) protected-path check before routing — FR-31: anchor wins;
(2) routing via `rules/routing.py`; (3) budget check after routing — FR-17: step keeps
the status routing chose. `re_check` is the Operator's *Accept* path; `_spend_and_budget`
parks `budget` on top of whatever `route` decided (FR-17).

**`done` still means "observed".** Gate is `liveness`; green only when `verify` says so.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from orchestrator.application.rules import budget, protected_paths, routing
from orchestrator.application.rules.signals import accepted_files
from orchestrator.application.steps import agent_workdir
from orchestrator.application.steps.context import (
    StepContext,
    committed,
    require_env,
    require_run,
    require_workspace,
    resolved_text,
)
from orchestrator.application.story_file import StoryFile, parse
from orchestrator.application.templates.agent_row import (
    EXPECT_KEY,
    RETRY_KEY,
    SPEC_CHECKPOINT_KEY,
    SPEC_FOLDER_KEY,
    STORY_ID_KEY,
)
from orchestrator.application.use_cases.spend import record_attempt_spend
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.values import Park, Retry, StepResult

#: The sub-keys of the two contracts, as `application/templates/agent_row.py:52-54` writes
#: them onto the row. `Retry`'s own field names, so the three below name one thing each.
EXPECT_FILES = "files"
RETRY_MAX = "max"
RETRY_PROMPT = "prompt"
RETRY_RESUME_SESSION = "resume_session"

#: The liveness glob FR-16 names, for a row whose `expect` declared none of its own. It
#: needs a spec folder to stand on: a row that resolves none globs nothing rather than the
#: filesystem root (Operator decision, 2026-09-27).
STORY_FILE_GLOB = "{spec_folder}/stories/{story_id}-*.md"

#: What a dispatch that ran past its deadline leaves. Not an exit code and not a route: the
#: harness never got to write a file, so there is nothing for FR-16 to read.
TIMED_OUT = "timeout {path} after {n} min"

#: FR-10: the stall detector found no filesystem activity under `cwd` for `n` minutes.
#: Verbatim format: `{path}` is the monitored worktree, `{n}` is `stall_min` (FR-10, NFR-8).
STALLED = "stalled {path}: no activity for {n} min"

#: What an anchor an attempt touched stops the Run with (AD-17), and how the files are named.
#: A sentence of its own rather than `git_commit.py`'s: that one is about a commit that was
#: refused, this one is about a dispatch that has already happened.
PROTECTED = "protected path modified: {paths}"
PATH_SEPARATOR = ", "

#: Where the hit list travels to the gate record: `StepResult.payload["hits"]`, one entry per
#: file, so the Operator's `continue` can name exactly the paths the Run reported (AD-9).
HITS_KEY = protected_paths.HITS_KEY

#: The signal a person answers a `protected_path` park with (AD-13). It carries the accepted
#: files under `rules/signals.py::FILES_KEY`; a `continue` on a checkpoint carries none.
CONTINUE_EVENT = "continue"

#: The field and value `claude -p --output-format json` puts on its result object when
#: `--max-budget-usd` stopped it (AD-10, FR-14). 5.11 confirmed this against the shipped
#: 2.1.258 bundle's own error-result schema: `subtype` carries `"error_max_budget_usd"` when
#: `terminal_reason === "budget_exhausted"` — `"max_budget"` occurs zero times in the bundle.
CAP_EXIT_FIELD = "subtype"
CAP_EXIT_VALUE = "error_max_budget_usd"


def finish(
    ctx: StepContext,
    attempt: Attempt,
    result: HarnessResult,
    timeout_min: float | None,
    stall_min: float | None = None,
) -> StepResult:
    """Record what the harness did, then say what the row reached; `mark_finished` runs
    first, so a killed attempt is as fully recorded as one that exited cleanly (AD-8).

    **A timeout is checked for anchors too, and it has to be.** The timeout park returns
    without routing, so a dispatch that edited an anchor and then hung would escape the check
    permanently rather than only this once: the Operator's *Retry* opens attempt 2, whose WIP
    commit commits that edit, and that commit falls *between* attempt 1's `end_sha` and
    attempt 2's `start_sha` — inside no agent range `walk_frame.py` collects, and gone
    from the tree the commit-guard reads. FR-31's "a modified anchor wins over every route"
    is the same sentence for this stop as for the routed ones.  The same applies to a stall.
    """
    finished = attempt.model_copy(
        update={
            "ended_at": ctx.ports.clock.now(),
            **agent_workdir.end_shas(ctx),
            "exit_code": result.exit_code,
            "session_id": result.session_id,
            "log_path": str(result.log_path),
            **usage(result),
        }
    )
    committed(ctx, lambda attempts: attempts.mark_finished(finished))
    if result.stalled:
        hit = protected(ctx, finished)
        if hit is not None:
            return hit.model_copy(update={"output_ref": str(result.log_path)})
        stall_path = result.stall_cwd if result.stall_cwd is not None else "(unknown)"
        stall_n = stall_min if stall_min is not None else 30
        reason = STALLED.format(path=stall_path, n=stall_n)
        return StepResult(
            status="error",
            gate=ctx.row.gate,
            output_ref=str(result.log_path),
            reason=reason,
            park=Park(kind="timeout", reason=reason, path=ctx.row.path),
        )
    if result.timed_out:
        hit = protected(ctx, finished)
        if hit is not None:
            return hit.model_copy(update={"output_ref": str(result.log_path)})
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

    `attempt` is the finished record, and the two checks marked below are its only readers
    here: the protected-path check compares the agent's range against `attempt.start_sha`,
    and the budget check reads the same attempt's usage and spend.
    """
    log = str(result.log_path)
    # 5.6 — the protected-path check, before the routing. FR-31: a modified anchor wins over
    # every route below, which it cannot do from behind one.
    hit = protected(ctx, attempt)
    if hit is not None:
        return hit.model_copy(update={"output_ref": log})
    files = story_files(ctx)
    if files is None:
        return StepResult(status="done", gate=ctx.row.gate, output_ref=log)
    routed = routing.route(
        _parsed(ctx, files),
        files,
        result.exit_code,
        bool(ctx.with_resolved.get(SPEC_CHECKPOINT_KEY)),
        ctx.row.retry_count,
        retry_of(ctx),
        contract=route_contract_of(ctx.with_resolved),
        gate=ctx.row.gate,
        path=ctx.row.path,
    )
    # 5.7 — the attempt's spend and the budget check go here, after the routing. FR-17: the
    # step keeps the status its file routed to and the Run parks on top of it.
    final = _spend_and_budget(ctx, attempt, result, routed)
    return final.model_copy(update={"output_ref": log})


def _spend_and_budget(
    ctx: StepContext, attempt: Attempt, result: HarnessResult, routed: StepResult
) -> StepResult:
    """FR-17, after `route` has already decided: record this attempt's spend, then park
    `budget` on top of whatever the row reached. A routed stop (`park` already set, e.g.
    `blocked`/`checkpoint`) keeps its own record and gets a second one via `budget_park`
    (`apply_step_result.budget_second_record`); a routed `done` or a retry-path `error`
    (no `park` of its own) gets the budget `Park` directly, and any `retry` is dropped —
    a Run parks instead of retrying once it is over budget.

    `ctx.ports.spend_writes` degrades like `tracer`: `None` skips the read entirely, which
    is every `StepPorts(...)` this story predates.
    """
    if ctx.ports.spend_writes is None:
        return routed
    run = require_run(ctx)
    with ctx.ports.spend_writes() as spend_ports:
        run = record_attempt_spend(spend_ports, run, attempt, result.usage)
    if _cap_exit(result):
        forced = budget.forced(run)
        return StepResult(status="error", gate=ctx.row.gate, reason=forced.reason, park=forced)
    park = budget.check(run)
    if park is None:
        return routed
    if routed.park is not None:
        return routed.model_copy(update={"budget_park": park})
    return routed.model_copy(update={"retry": None, "park": park})


def _cap_exit(result: HarnessResult) -> bool:
    """Whether the harness's own JSON result marks a `--max-budget-usd` cap stop."""
    raw = result.raw_result
    return isinstance(raw, Mapping) and raw.get(CAP_EXIT_FIELD) == CAP_EXIT_VALUE


def protected(ctx: StepContext, attempt: Attempt) -> StepResult | None:
    """AD-17 over this attempt's own range, or `None` when it touched no anchor.

    The range is `start_sha .. end_sha` — what the harness did between the SHA recorded
    before it started and the SHA recorded when it exited — unioned with whatever it left
    uncommitted, so a file written and never committed is as much a hit as a committed one.
    Nothing else is in scope: an operator commit and the orchestrator's own WIP and prepare
    commits are outside those two ends by construction, which is what makes this check
    deterministic rather than a guess about who wrote what. A `workdir` attempt spans two
    trees and `agent_workdir.changes` collects both, in one spelling, so everything below —
    the anchor set, `accepted_paths`, the reason sentence, the payload — is unchanged.

    A hit is never retried. `apply_step_result` parks the Run on it (AD-8) and the Operator
    answers with *Accept* or a skip; `re_check` below is what an Accept comes back to.
    """
    environment = require_env(ctx)
    allowed = (*environment.accepted_paths, *protected_paths.declared(ctx.row.with_resolved))
    hits = protected_paths.check(agent_workdir.changes(ctx, attempt), environment.anchors, allowed)
    if not hits:
        return None
    reason = PROTECTED.format(paths=PATH_SEPARATOR.join(hit.path for hit in hits))
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        reason=reason,
        park=Park(kind="protected_path", reason=reason, path=ctx.row.path),
        payload=protected_paths.hits_payload(hits),
    )


def re_check(ctx: StepContext) -> StepResult | None:
    """The Accept branch (AD-9): a `continue` carrying files re-runs the tail, dispatching
    nothing. `None` for every other resume, which is the ordinary dispatch.

    The Operator answered a `protected_path` park by accepting the paths, so the work the
    row was doing is already in the worktree — re-dispatching would ask the harness to do it
    again, and would put a WIP commit and a prepare commit in front of a range the check is
    about to read. What is left is the check and the routing, over the *previous* attempt's
    own two SHAs, with `run.accepted_paths` — which `signal_run` has already extended —
    excluded.

    The discriminator is `StepContext` alone, as AD-9 requires: the event plus a payload that
    carries files. A `continue` on a `checkpoint` park carries none, and a row whose first
    attempt was resumed has no range to re-read.
    """
    signal, previous = ctx.resume_signal, ctx.previous_attempt
    if signal is None or signal.event != CONTINUE_EVENT or previous is None:
        return None
    if not accepted_files(signal.payload):
        return None
    return tail(ctx, previous, _reported(previous))


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
    for pattern in liveness_globs(ctx.with_resolved):
        found.update(workspace.glob(pattern))
    return tuple(sorted(found))


def liveness_globs(with_resolved: Mapping[str, Any]) -> tuple[str, ...]:
    """`expect.files` as the planner resolved it (AD-7), or FR-16's own glob for a row whose
    Template declared no `files` at all — or nothing, for a row with no `expect` mapping or
    with a spec folder that resolved empty, whose fallback would otherwise be the absolute
    `/stories/-*.md` (Operator decision, 2026-09-27)."""
    expect = with_resolved.get(EXPECT_KEY)
    if not isinstance(expect, Mapping):
        return ()
    declared = tuple(str(pattern) for pattern in expect.get(EXPECT_FILES) or ())
    if declared:
        return declared
    spec_folder = resolved_text(with_resolved, SPEC_FOLDER_KEY)
    if not spec_folder:
        return ()
    return (
        STORY_FILE_GLOB.format(
            spec_folder=spec_folder,
            story_id=resolved_text(with_resolved, STORY_ID_KEY),
        ),
    )


def route_contract_of(with_resolved: Mapping[str, Any]) -> routing.RouteContract:
    """The row's declared result contract, or FR-16's defaults when it declares no lists
    (Operator decision, 2026-09-27) — the mirror of `retry_of`, pure over the mapping so
    the terminal poll can ask the same question of a parked row.

    `misconfigured_when` rides along either way: a row may keep the default tokens and
    still name the conditions that are a broken installation rather than a question.
    """
    expect = with_resolved.get(EXPECT_KEY)
    declared = expect if isinstance(expect, Mapping) else {}
    lists = {
        key: tuple(str(token) for token in declared.get(key) or ())
        for key in ("success", "blocked", "checkpoint", "misconfigured_when")
    }
    conditions = lists["misconfigured_when"]
    if not (lists["success"] or lists["blocked"] or lists["checkpoint"]):
        return routing.RouteContract(
            success=routing.DEFAULT.success,
            blocked=routing.DEFAULT.blocked,
            checkpoint=routing.DEFAULT.checkpoint,
            misconfigured_when=conditions,
        )
    return routing.RouteContract(
        success=lists["success"],
        blocked=lists["blocked"],
        checkpoint=lists["checkpoint"],
        misconfigured_when=conditions,
    )


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


def _reported(attempt: Attempt) -> HarnessResult:
    """What the dispatch that parked already reported, rebuilt from its own attempt row.

    The Accept branch runs no harness, and `tail` takes what one returned: the exit code and
    the log are the attempt's columns (AD-8's `mark_finished` wrote them), so the routing
    reads exactly what it read the first time. `usage` is left out on purpose — the spend of
    that dispatch was recorded against that dispatch, and 5.7 must not count it twice.
    """
    return HarnessResult(
        session_id=attempt.session_id or "",
        exit_code=attempt.exit_code,
        log_path=Path(attempt.log_path or ""),
    )


def _parsed(ctx: StepContext, files: tuple[str, ...]) -> StoryFile | None:
    """The one match, read and parsed — or `None`, which liveness reports rather than routes.

    A file that vanished between the glob and the read is `""`, which parses to `None`: the
    same answer as one whose frontmatter is unreadable, and the same stop.
    """
    if len(files) != 1:
        return None
    return parse(files[0], require_workspace(ctx, ctx.cwd).read(files[0]) or "")
