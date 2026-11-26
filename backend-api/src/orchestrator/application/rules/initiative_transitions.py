"""What follows a done Run of an initiative, as pure functions of the frozen sequence (AD-37).

The classification reads only the frozen entry (its `type`, `shown_as` and `steps`), never a
workflow name, a template name or a step id. No I/O.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Any

from orchestrator.application.preflight.model import (
    CHECK_EPICS_YAML,
    CHECK_EXISTING_STORY_FILES,
    CHECK_SPEC_MD,
    CHECK_STORIES_YAML,
    PreflightResult,
)
from orchestrator.application.steps import CONVERSATION_KIND
from orchestrator.domain.entities.initiative import FrozenSequence, FrozenWorkflow
from orchestrator.domain.entities.project_package import StepDecl
from orchestrator.domain.entities.step_run import StepRun

FEAT_PREFIX = "feat"
NO_PROJECT_BUDGET = "no project budget"
NO_VERDICT = "no gate verdict"
UNDECLARED_WORD = "gate word {word} is not declared"
NO_OWNER = "gate failed with no owner"
FOREIGN_OWNER = "gate owner {owner} is not a step of {template}"
NO_TRANSITION = "no transition for {workflow}"
PREFLIGHT_BLOCK = "preflight: {check}: {text}"
FEAT_NOT_FROM_MAIN = "feat/{slug} exists and is not from main; delete it or reopen"
SPEC_FILE_CHECKS = frozenset(
    {CHECK_EPICS_YAML, CHECK_STORIES_YAML, CHECK_SPEC_MD, CHECK_EXISTING_STORY_FILES}
)
EPICS_FILE = "epics.yaml"
DEFECT_PREFIX = "- "
INTERACTIVE = "interactive"
AUTO = "auto"
REOPEN_NO_REASON = "a reopen needs a reason"
REOPEN_NOT_A_STEP = "step {step} is not a conversation step of this initiative's sequence"
REOPEN_CLOSED = "initiative {slug} is {state}; nothing reopens"
REOPEN_REASON = "reopen"
BRANCH_ATTACHED = "attached"
BRANCH_CREATED = "created"


def is_spec(entry: FrozenWorkflow) -> bool:
    return entry.type == INTERACTIVE and any(s.kind == CONVERSATION_KIND for s in entry.steps)


def is_merge(entry: FrozenWorkflow) -> bool:
    return entry.type == INTERACTIVE and entry.shown_as == "step" and not is_spec(entry)


def spec_index(sequence: FrozenSequence, position: int) -> int | None:
    """The last spec entry at or before `position`."""
    found = [i for i, entry in enumerate(sequence.workflows[: position + 1]) if is_spec(entry)]
    return found[-1] if found else None


def first_auto_after(sequence: FrozenSequence, index: int | None) -> int | None:
    if index is None:
        return None
    for i in range(index + 1, len(sequence.workflows)):
        if sequence.workflows[i].type == AUTO:
            return i
    return None


def is_build(sequence: FrozenSequence, position: int) -> bool:
    return position == first_auto_after(sequence, spec_index(sequence, position))


def owners_in_order(owners: Sequence[str], entry: FrozenWorkflow) -> list[str]:
    """The owners the entry declares, in the entry's own step order."""
    return [step.id for step in entry.steps if step.id in owners]


def foreign_owner(owners: Sequence[str], entry: FrozenWorkflow) -> str | None:
    declared = {step.id for step in entry.steps}
    return next((owner for owner in owners if owner not in declared), None)


def tech_step(rows: Sequence[StepRun]) -> str | None:
    """The conversation step that writes `epics.yaml`, else the last conversation step."""
    talks = [row for row in rows if row.kind == CONVERSATION_KIND]
    for row in talks:
        writes: Any = row.with_resolved.get("writes") or ()
        if any(str(path).rsplit("/", 1)[-1] == EPICS_FILE for path in writes):
            return str(row.with_resolved.get("step"))
    return str(talks[-1].with_resolved.get("step")) if talks else None


def preflight_failure(result: PreflightResult) -> tuple[list[str], str | None]:
    """The spec-file defect lines, and the block text of the first other failing line."""
    defects: list[str] = []
    other: str | None = None
    for line in result.lines:
        if line.status != "fail":
            continue
        if line.check in SPEC_FILE_CHECKS:
            defects.append(f"{line.check}: {line.text}")
        elif other is None:
            other = PREFLIGHT_BLOCK.format(check=line.check, text=line.text)
    if result.plan_error is not None and not any(str(result.plan_error) in d for d in defects):
        defects.append(str(result.plan_error))
    return defects, other


def offered_inputs(declared: Collection[str], offered: Mapping[str, object]) -> dict[str, object]:
    """Only the names the template declares, and never a `None`."""
    return {k: v for k, v in offered.items() if k in declared and v is not None}


def defect_count(message: str) -> int:
    return sum(1 for line in message.splitlines() if line.startswith(DEFECT_PREFIX))


def reopen_round_steps(
    entry_steps: Sequence[StepDecl], done_steps: Collection[str], step_id: str
) -> tuple[str, ...]:
    """The reopened step, then every later conversation step of the entry not yet done."""
    ids = [step.id for step in entry_steps]
    later = entry_steps[ids.index(step_id) + 1 :] if step_id in ids else ()
    return (
        step_id,
        *(s.id for s in later if s.kind == CONVERSATION_KIND and s.id not in done_steps),
    )
