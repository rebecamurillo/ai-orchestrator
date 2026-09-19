"""The walker: one pinned Template tree in, one flat list of rows out (AD-7).

Pure. Everything that touches the outside world goes through `PlanReader`, and everything
that decides what a row *is* is one function here, so a rule can be read without reading
the traversal it happens inside.

**The path.** A top-level step is its own id; a `for_each` element `i` prefixes
`{loop_id}[{i}]`; a `template` call inside a loop contributes no segment, and one at the
top level contributes its id — so `initiative@1` reads `epics[0].stories[3].build` where
`epic@1` reads `stories[3].build`, the same Story named from two depths with no
per-Template rule. `PlannedRow.frame` is that prefix wherever the row is inside a loop and
`None` otherwise, which is what `in_loop` is for: a call's own id is a path segment, not a
frame — nobody skips "the `sub` frame". The label follows the same shape,
`epic 1 · story 4-1 · build`, with the step's id read as words; a checkpoint the planner
inserted reads `… · done checkpoint` or `… · before`, because "after" is not the question.

**Two rows the planner inserts, and one flag it does not.** `pause_before_item_when` and
`pause_after_item_when` are stops in their own right, so each becomes a `checkpoint` row,
and only where the item's field is truthy. `pause_when` on an `agent` step is not a stop
before or after that step but how it behaves, so it stays a flag and adds no row.

**A call is dispatched on its `call`, not on its kind.** A `uses: template` step always
carries one and no other step ever does, so the narrowing the walker needs anyway is also
the test — and AD-9's "no `if kind == …`" is kept without a fourth kind constant.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from orchestrator.application.dto import RunInputs
from orchestrator.application.graph import UNVALIDATED
from orchestrator.application.steps import CHECKPOINT_KIND, SHELL_KIND
from orchestrator.application.templates.agent_row import (
    PROMPT_EXTRA_KEY,
    agent_extras,
    prompt_extra,
)
from orchestrator.application.templates.branches import BranchAllocator, fresh_params
from orchestrator.application.templates.lists import (
    EPICS_KIND,
    ID_KEY,
    STORIES_KIND,
    check_entries,
    list_kind,
    read_list,
    stories_directory,
    story_done,
)
from orchestrator.application.templates.model import (
    ForEach,
    ParsedTemplate,
    Step,
    TemplateCall,
)
from orchestrator.application.templates.plan_model import (
    AFTER_ITEM,
    AFTER_LABEL,
    BEFORE_ITEM,
    CALLEE_NOT_RESOLVED,
    INSERTED_GATE,
    LABEL_SEPARATOR,
    ON_FAIL_KEY,
    PATH_SEPARATOR,
    REASON_ALREADY_DONE,
    PlanError,
    Redispatched,
    ResolvedTree,
    working_branch,
)
from orchestrator.application.templates.reader import PlanReader
from orchestrator.application.templates.skip_reason import empty_command_reason
from orchestrator.application.templates.substitute import paused, resolve
from orchestrator.domain.statuses import StepStatus
from orchestrator.domain.values import PlannedRow

#: The two statuses a row can be born in. Everything else is 4.6's to write (AD-8).
PLANNED: StepStatus = "planned"
SKIPPED: StepStatus = "skipped"

#: What a row's `seq` reads until `plan_run` numbers the whole list densely from 1.
UNNUMBERED = 0

#: The `with` key a `run:` desugars into.
COMMAND_KEY = "command"

#: The key the planner writes onto every timed row's `with_resolved`. The `agent` keys
#: are `agent_row`'s, because only that kind has them.
TIMEOUT_KEY = "timeout_min"

#: The key the planner writes onto agent rows' `with_resolved` for the stall detector.
STALL_KEY = "stall_min"

#: What one loop item is called in a label: the Story by its own id, the epic by its place.
STORY_LABEL = "story"
EPIC_LABEL = "epic"

#: What a step id's `_` reads as in a label. No shipped id has one — a slug has no `_` —
#: but the rule is the rule, and `commit-guard` keeps its hyphen either way.
LABEL_WORD_SEPARATOR = " "
ID_WORD_SEPARATOR = "_"


@dataclass(frozen=True)
class Frame:
    """Where the walker is: what it prefixes, what it reads, and what it has bound.

    One object rather than eight arguments, and frozen, so a nested frame is a
    `replace(...)` of its parent and no rule can write back into the frame above it.
    `ref` is the commit every file read in this frame is read at — a frame never mixes
    two — and `scope` is what a `{{ }}` here resolves against: a callee sees only what its
    caller passed it (AD-15).
    """

    #: The path prefix every row in this frame carries; `""` at the top of the root file.
    prefix: str
    #: One label segment per loop this frame is inside, outermost first.
    labels: tuple[str, ...]
    ref: str
    scope: Mapping[str, Any]
    #: The Template this frame's steps come from; what a `PlanError` names.
    template: ParsedTemplate
    story_id: str | None = None
    #: True when the whole frame is `already done`, so every row of it is skipped (FR-10).
    skipped: bool = False
    #: The branch this Template works on, used to find a list file the base does not hold.
    #: What the file *declared*: the name the plan is read at, never the name created.
    branch: str | None = None
    #: The name this Run creates instead (`branches.py`), carried by every `git.*` row of
    #: the frame. `None` for a Template that checks nothing out.
    fresh_branch: str | None = None
    #: Where that fresh branch begins — the declared branch when the remote holds it, so
    #: the worktree holds the tree the plan was read from.
    fresh_from: str | None = None
    #: True inside a `for_each` item: what makes `PlannedRow.frame` a frame and not a path.
    in_loop: bool = False
    #: The name the enclosing loop bound its entry under, where the entry is this file's
    #: own; a callee reads its entry off the `item` input its caller bound instead.
    item_name: str | None = None


@dataclass(frozen=True)
class Context:
    """What the whole walk shares: the pinned tree, the Run's inputs, and the one reader."""

    tree: ResolvedTree
    inputs: RunInputs
    reader: PlanReader
    #: One fresh name per declared branch, for the whole walk (AD-7, `branches.py`).
    allocator: BranchAllocator
    #: The BMAD version this instance runs; carried for the executors 4.5 builds from a row.
    bmad_version: str


@dataclass(frozen=True)
class _Item:
    """One element of a `for_each`, and everything the element's frame is built from."""

    loop: ForEach
    index: int
    entry: Mapping[str, Any]
    #: Which list the loop read, by basename — `None` for a loop over anything else.
    kind: str | None
    #: The resolved path of the list file, which is also where the story folder sits.
    path: str


def expand(entries: Sequence[Step | ForEach], frame: Frame, ctx: Context) -> list[PlannedRow]:
    """Every row one `steps:` list produces, in file order."""
    rows: list[PlannedRow] = []
    for entry in entries:
        if isinstance(entry, ForEach):
            rows += expand_loop(entry, frame, ctx)
        elif entry.call is not None:
            rows += expand_call(entry, entry.call, frame, ctx)
        else:
            rows.append(step_row(entry, frame))
    return rows


def expand_loop(loop: ForEach, frame: Frame, ctx: Context) -> list[PlannedRow]:
    """One frame per entry of the list file the loop names, in the file's own order."""
    path = str(resolve(loop.source, frame.scope))
    items, ref_used = read_list(ctx.reader, frame, path, line=loop.line)
    kind = list_kind(path)
    check_entries(items, kind, frame, line=loop.line)
    # the list decided which commit this frame reads at; the story files follow it
    outer = replace(frame, ref=ref_used)
    rows: list[PlannedRow] = []
    for index, entry in enumerate(items):
        item = _Item(loop=loop, index=index, entry=entry, kind=kind, path=path)
        rows += _item_rows(item, _item_frame(item, outer, ctx), ctx)
    return rows


def expand_call(step: Step, call: TemplateCall, frame: Frame, ctx: Context) -> list[PlannedRow]:
    """A call is not a row: its callee's steps are inlined under the caller's scope.

    The call arrives beside its step because `expand` has already narrowed it — see the
    module docstring on why a call is recognised by its `call` rather than by its kind.
    """
    callee = ctx.tree.callee(call.name, call.version)
    if callee is None:
        raise PlanError(
            reason=CALLEE_NOT_RESOLVED,
            template=frame.template.name,
            version=frame.template.version,
            line=call.line,
            item=f"{call.name}@{call.version}",
        )
    scope = {name: resolve(value, frame.scope) for name, value in call.inputs}
    declared = working_branch(callee, scope)
    inner = replace(
        frame,
        prefix=frame.prefix if frame.in_loop else _joined(frame.prefix, step.id),
        scope=scope,
        template=callee,
        branch=declared,
        fresh_branch=ctx.allocator.fresh(declared),
        fresh_from=ctx.allocator.start_point(declared, ctx.inputs.base_branch),
        item_name=None,
    )
    return expand(callee.steps, inner, ctx)


def step_row(step: Step, frame: Frame) -> PlannedRow:
    """One executable step as the row that will run it."""
    resolved = _resolved(step, frame)
    status, reason = row_status(step, frame, resolved)
    return PlannedRow(
        seq=UNNUMBERED,
        path=_joined(frame.prefix, step.id),
        label=_label(frame, step.id.replace(ID_WORD_SEPARATOR, LABEL_WORD_SEPARATOR)),
        kind=step.uses,
        # what the file declared, or the word for "the file declared nothing" (NFR-2)
        gate=step.gate or UNVALIDATED,
        status=status,
        reason=reason,
        with_resolved=resolved,
        frame=frame.prefix if frame.in_loop else None,
        story_id=frame.story_id,
    )


def checkpoint_row(frame: Frame, position: str) -> PlannedRow:
    """The stop a `pause_*_item_when` declares: one row per item, inside the item's frame.

    The Operator wrote the pause, so the gate is the `checkpoint` kind's own and never
    `unvalidated` — nothing here was left ungated.
    """
    skipped = frame.skipped
    return PlannedRow(
        seq=UNNUMBERED,
        path=_joined(frame.prefix, position),
        label=_label(frame, AFTER_LABEL if position == AFTER_ITEM else position),
        kind=CHECKPOINT_KIND,
        gate=INSERTED_GATE[CHECKPOINT_KIND],
        status=SKIPPED if skipped else PLANNED,
        reason=REASON_ALREADY_DONE if skipped else None,
        with_resolved={},
        frame=frame.prefix,
        story_id=frame.story_id,
    )


def row_status(
    step: Step, frame: Frame, resolved: Mapping[str, Any]
) -> tuple[StepStatus, str | None]:
    """What a row is born as, and why — the two rules that skip a row at plan time."""
    if frame.skipped:
        return SKIPPED, REASON_ALREADY_DONE
    if step.uses == SHELL_KIND and not str(resolved.get(COMMAND_KEY) or "").strip():
        return SKIPPED, empty_command_reason(dict(step.params).get(COMMAND_KEY))
    return PLANNED, None


# --- one item of a loop ---------------------------------------------------------------------


def _item_frame(item: _Item, frame: Frame, ctx: Context) -> Frame:
    """The frame one element of a loop expands inside."""
    return replace(
        frame,
        prefix=_joined(frame.prefix, f"{item.loop.id}[{item.index}]"),
        labels=(*frame.labels, _item_label(item)),
        scope={**frame.scope, item.loop.as_name: item.entry},
        item_name=item.loop.as_name,
        story_id=_story_id(item) or frame.story_id,
        skipped=frame.skipped or _already_done(item, frame, ctx),
        in_loop=True,
    )


def _item_rows(item: _Item, frame: Frame, ctx: Context) -> list[PlannedRow]:
    """`[before?] + the loop's steps + [after?]` — the pauses belong inside the frame."""
    rows: list[PlannedRow] = []
    if paused(item.loop.pause_before_item_when, frame.scope):
        rows.append(checkpoint_row(frame, BEFORE_ITEM))
    rows += expand(item.loop.steps, frame, ctx)
    if paused(item.loop.pause_after_item_when, frame.scope):
        rows.append(checkpoint_row(frame, AFTER_ITEM))
    return rows


def _item_label(item: _Item) -> str:
    """`story {id}` names the Story an Operator knows; the rest count from one."""
    if item.kind == STORIES_KIND:
        return f"{STORY_LABEL} {item.entry[ID_KEY]}"
    if item.kind == EPICS_KIND:
        return f"{EPIC_LABEL} {item.index + 1}"
    return f"{item.loop.as_name} {item.index + 1}"


def _story_id(item: _Item) -> str | None:
    """The Story a row inside this frame belongs to; `None` for a loop over anything else."""
    if item.kind != STORIES_KIND:
        return None
    return str(item.entry[ID_KEY])


def _already_done(item: _Item, frame: Frame, ctx: Context) -> bool:
    """FR-10: a Story whose file is already `done` is skipped, unless this is a re-review.

    The lookup happens either way, and only its *answer* is dropped on a re-review: two
    files matching one Story's `{id}-*.md` is a fact about the repository, not about what
    the Operator asked for, and a plan that refused it yesterday must not plan it today
    because a box was ticked.
    """
    story = _story_id(item)
    if story is None:
        return False
    done = story_done(ctx.reader, frame, stories_directory(item.path), story, item.loop.line)
    return done and not ctx.inputs.re_review_done


# --- one row --------------------------------------------------------------------------------


def _resolved(step: Step, frame: Frame) -> dict[str, Any]:
    """The step's `with`, substituted, plus what a complete plan has nowhere else to put.

    `timeout_min` is written here because `PlannedRow` has no field for it and AD-7 says a
    row carries everything that decides what it does; a kind that times nothing writes none.
    """
    resolved = {key: resolve(value, frame.scope) for key, value in step.params}
    timeout = step.timeout_min if step.timeout_min is not None else step.meta.timeout_default_min
    if timeout is not None:
        resolved[TIMEOUT_KEY] = timeout
    stall = step.stall_min if step.stall_min is not None else step.meta.stall_default_min
    if stall is not None:
        resolved[STALL_KEY] = stall
    routing = _routing(step, frame)
    if routing is not None:
        resolved[ON_FAIL_KEY] = routing
    if step.agent is not None:
        resolved.update(agent_extras(step.agent, frame))
        resolved[PROMPT_EXTRA_KEY] = prompt_extra(resolved, frame)
    return fresh_params(step, frame, resolved)


def _routing(step: Step, frame: Frame) -> str | Redispatched | None:
    """How this row's failure is routed, in the form 4.7's executors read (AD-9).

    A plain action is the word the file wrote. A redispatch is the one form that needs
    work: the file names a step id and the executor needs a `seq`, so the target is
    resolved **inside this row's own frame** — `stories[3].verify` goes back to
    `stories[3].build` and never to another Story's — and `plan_run` numbers it once the
    walk is done. A step that declared nothing is left out entirely, which the executor
    reads as the DSL's own default, `escalate`.
    """
    if step.redispatch is None:
        return step.on_fail
    return Redispatched(
        target_path=_joined(frame.prefix, step.redispatch),
        max=step.redispatch_max,
        template=frame.template.name,
        version=frame.template.version,
        line=step.line,
    )


def _joined(prefix: str, segment: str) -> str:
    """A path under its enclosing prefix, or on its own at the top of the root file."""
    return f"{prefix}{PATH_SEPARATOR}{segment}" if prefix else segment


def _label(frame: Frame, last: str) -> str:
    """One label segment per loop the row is inside, then the row's own name."""
    return LABEL_SEPARATOR.join((*frame.labels, last))
