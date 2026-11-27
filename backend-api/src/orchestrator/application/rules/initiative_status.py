"""The status of an initiative, computed from its Runs and advances (AD-36 "The status").

Pure. The table is an ordered sequence of row functions; the first that answers wins.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from orchestrator.application.rules.attention import STEP_NOT_CLOSED, Attention
from orchestrator.application.steps import CONVERSATION_KIND
from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.domain.entities.run import Run

InitiativeStatusValue = Literal["running", "waiting for her", "done", "failed", "cancelled"]

WAITING_FOR_SLOT = "waiting for a slot"
UNMAPPED_WORD = "unmapped word {word}"
RUN_CANCELLED = "Run cancelled"
WAITING_FOR_MERGE = "waiting for the pull request merge"
NEXT_WORKFLOW = "next workflow starting"

_RUNNING_ATTENTION: tuple[Attention, ...] = ("your_turn", "answering", "queued")


@dataclass(frozen=True)
class RunFacts:
    run: Run
    attention: Attention | None
    step: str | None
    step_word: str | None


@dataclass(frozen=True)
class StatusReading:
    status: InitiativeStatusValue
    step: str
    reason: str


@dataclass(frozen=True)
class _Ctx:
    initiative: Initiative
    latest: RunFacts | None
    advances: Sequence[InitiativeAdvance]
    mapping: Mapping[str, str]
    build: RunFacts | None


_Row = Callable[[_Ctx], tuple[InitiativeStatusValue, str] | None]


def initiative_status(
    initiative: Initiative,
    runs: Sequence[RunFacts],
    advances: Sequence[InitiativeAdvance],
    mapping: Mapping[str, str],
) -> StatusReading:
    latest = _latest(runs)
    ctx = _Ctx(initiative, latest, advances, mapping, _build_facts(initiative, runs))
    status, reason = next(found for row in _ROWS if (found := row(ctx)) is not None)
    return StatusReading(status, _step(initiative, latest), reason)


def _latest(runs: Sequence[RunFacts]) -> RunFacts | None:
    return max(runs, key=lambda f: f.run.created_at, default=None)


def build_index(initiative: Initiative) -> int | None:
    workflows = initiative.sequence.workflows
    spec = next(
        (
            i
            for i, w in enumerate(workflows)
            if w.type == "interactive" and any(s.kind == CONVERSATION_KIND for s in w.steps)
        ),
        None,
    )
    if spec is None:
        return None
    return next((i for i in range(spec + 1, len(workflows)) if workflows[i].type == "auto"), None)


def _build_facts(initiative: Initiative, runs: Sequence[RunFacts]) -> RunFacts | None:
    index = build_index(initiative)
    if index is None:
        return None
    return _latest([f for f in runs if f.run.initiative_position == index])


def _step(initiative: Initiative, latest: RunFacts | None) -> str:
    workflows = initiative.sequence.workflows
    if latest is not None and latest.step:
        return latest.step
    position = latest.run.initiative_position if latest is not None else None
    if position is not None and 0 <= position < len(workflows):
        return workflows[position].workflow
    return workflows[0].workflow if workflows else ""


def _cancelled(ctx: _Ctx) -> tuple[InitiativeStatusValue, str] | None:
    return ("cancelled", "") if ctx.initiative.cancelled_at is not None else None


def _merged(ctx: _Ctx) -> tuple[InitiativeStatusValue, str] | None:
    return ("done", "") if ctx.initiative.pr_merged_at is not None else None


def _blocked_advance(ctx: _Ctx) -> tuple[InitiativeStatusValue, str] | None:
    for advance in ctx.advances:
        if advance.consumed_at is None and advance.blocked_reason:
            return "waiting for her", advance.blocked_reason
    return None


def _queued_or_running(ctx: _Ctx) -> tuple[InitiativeStatusValue, str] | None:
    facts = ctx.latest
    if facts is None:
        return None
    if facts.run.status == "queued":
        return "running", WAITING_FOR_SLOT
    if facts.run.status != "running":
        return None
    word = facts.step_word
    if word is not None and word not in ctx.mapping:
        return "failed", UNMAPPED_WORD.format(word=word)
    return "running", ""


def _conversation_stop(ctx: _Ctx) -> tuple[InitiativeStatusValue, str] | None:
    facts = ctx.latest
    if facts is None or facts.run.status != "needs_you" or facts.run.park_kind != CONVERSATION_KIND:
        return None
    if facts.attention == "blocked":
        reason = facts.run.park_reason or ""
        return "waiting for her", reason if reason.startswith(STEP_NOT_CLOSED) else ""
    if facts.attention in _RUNNING_ATTENTION:
        return "running", ""
    return None


def _other_stop(ctx: _Ctx) -> tuple[InitiativeStatusValue, str] | None:
    facts = ctx.latest
    if facts is None or facts.run.status != "needs_you":
        return None
    return "waiting for her", facts.run.park_reason or ""


def _failed(ctx: _Ctx) -> tuple[InitiativeStatusValue, str] | None:
    return ("failed", "") if ctx.latest and ctx.latest.run.status == "failed" else None


def _run_cancelled(ctx: _Ctx) -> tuple[InitiativeStatusValue, str] | None:
    return (
        ("failed", RUN_CANCELLED) if ctx.latest and ctx.latest.run.status == "cancelled" else None
    )


def _build_done(ctx: _Ctx) -> tuple[InitiativeStatusValue, str] | None:
    if ctx.build is not None and ctx.build.run.status == "done":
        return "running", WAITING_FOR_MERGE
    return None


def _otherwise(_ctx: _Ctx) -> tuple[InitiativeStatusValue, str] | None:
    return "running", NEXT_WORKFLOW


_ROWS: tuple[_Row, ...] = (
    _cancelled,
    _merged,
    _blocked_advance,
    _queued_or_running,
    _conversation_stop,
    _other_stop,
    _failed,
    _run_cancelled,
    _build_done,
    _otherwise,
)
