"""What the initiative views and the Board both read off one Run (AD-36 "Attention", SPEC
"The step word").

Pure over values already read; the one port touched is the workspace factory, for the step
word's file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from orchestrator.application import story_file
from orchestrator.application.rules import attention as attention_rule
from orchestrator.application.rules import conversation, session
from orchestrator.application.rules.initiative_status import RunFacts
from orchestrator.application.rules.signals import row_at
from orchestrator.application.steps import CONVERSATION_KIND
from orchestrator.application.steps.context import WorkspaceFactory
from orchestrator.application.templates.lines import load_with_lines
from orchestrator.application.templates.table import DEFAULT_TEMPLATE_TYPE, TEMPLATE_TYPE_KEY
from orchestrator.application.use_cases.initiative_view_types import InitiativeTag
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.initiative import FrozenSequence, Initiative
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.templates import TemplateVersionRepository
from orchestrator.domain.ports.workspace import WorkspaceError

_NOT_SETTLED = ("planned", "queued", "running")
_GLOB_CHARACTERS = "*?[{"


def current_conversation_row(run: Run, rows: Sequence[StepRun]) -> StepRun | None:
    """The `conversation` row the Run is on, or last was on."""
    talks = [row for row in rows if row.kind == CONVERSATION_KIND]
    running = next((row for row in talks if row.status == "running"), None)
    if running is not None:
        return running
    if run.park_kind == CONVERSATION_KIND:
        parked = row_at(rows, run.park_path)
        if parked is not None:
            return parked
    settled = [row for row in talks if row.status not in _NOT_SETTLED]
    return max(settled, key=lambda row: row.seq, default=None)


def conversation_step(row: StepRun) -> str:
    return str(row.with_resolved.get(conversation.STEP_KEY) or "")


def step_word(run: Run, row: StepRun | None, workspace: WorkspaceFactory | None) -> str | None:
    """The `status` the row's expected file declares, or `None` when anything is missing."""
    if workspace is None or row is None or not run.worktree_path:
        return None
    path = _expected_file(row)
    if path is None:
        return None
    # The file is agent-written: a link is not followed, and a path the workspace refuses
    # reads as no word rather than failing every Board and list read.
    tree = workspace(run.worktree_path)
    try:
        text = None if tree.is_link(path) else tree.read_lenient(path)
    except WorkspaceError:
        return None
    parsed = None if text is None else story_file.parse(path, text)
    return None if parsed is None else parsed.status


def _expected_file(row: StepRun) -> str | None:
    expect = row.with_resolved.get("expect")
    files = expect.get("files") if isinstance(expect, Mapping) else None
    first = files[0] if isinstance(files, list | tuple) and files else None
    if not isinstance(first, str) or not first or any(c in first for c in _GLOB_CHARACTERS):
        return None
    return first


def run_facts(
    run: Run,
    rows: Sequence[StepRun],
    attempts: Sequence[Attempt],
    workspace: WorkspaceFactory | None,
) -> RunFacts:
    row = current_conversation_row(run, rows)
    word = step_word(run, row, workspace)
    return RunFacts(
        run=run,
        attention=attention_rule.attention(run, rows, attempts, step_word=word),
        step=None if row is None else conversation_step(row),
        step_word=word,
    )


def session_turns(row: StepRun, attempts: Sequence[Attempt]) -> list[Attempt]:
    turns = [a for a in attempts if a.step_run_id == row.id and a.role == session.SESSION_ROLE]
    return sorted(turns, key=lambda attempt: attempt.n)


def ended_turns(turns: Sequence[Attempt]) -> list[Attempt]:
    return [turn for turn in turns if turn.status not in ("queued", "running")]


def shown_indices(sequence: FrozenSequence) -> list[int]:
    return [i for i, entry in enumerate(sequence.workflows) if entry.shown_as == "workflow"]


def shown_number(sequence: FrozenSequence, position: int | None) -> int:
    """The 1-based number of the shown workflow holding `position`, at least 1."""
    if position is None:
        return 1
    return max(1, sum(1 for index in shown_indices(sequence) if index <= position))


def initiative_tag(initiative: Initiative, run: Run, step: str | None) -> InitiativeTag:
    return InitiativeTag(
        id=initiative.id,
        slug=initiative.slug,
        step=step,
        position=shown_number(initiative.sequence, run.initiative_position),
        workflow_count=len(shown_indices(initiative.sequence)),
    )


def template_type_of(
    templates: TemplateVersionRepository | None,
    name: str,
    version: int,
    memo: dict[tuple[str, int], str | None],
) -> str | None:
    """The root template version's `type`, read once per `(name, version)` through `memo`."""
    if templates is None:
        return None
    key = (name, version)
    if key not in memo:
        stored = templates.get(name, version)
        root = None if stored is None else load_with_lines(stored.yaml).root
        found = DEFAULT_TEMPLATE_TYPE if root is None else root.get(TEMPLATE_TYPE_KEY)
        memo[key] = None if stored is None else str(found or DEFAULT_TEMPLATE_TYPE)
    return memo[key]


def entry_steps(sequence: FrozenSequence, index: int) -> list[tuple[str, str]]:
    """`(id, kind)` of what the workflow at `index` shows: its declared steps, then one
    `automatic` step per `shown_as: step` entry that follows it directly."""
    entries = sequence.workflows
    steps: list[tuple[str, str]] = [(decl.id, decl.kind) for decl in entries[index].steps]
    for entry in entries[index + 1 :]:
        if entry.shown_as != "step":
            break
        steps.append((entry.workflow, "automatic"))
    return steps
