"""The build a reopen cancelled, read from the gate records the detail already loaded (SPEC CAP-2).

While the spec Run of a round is not `done`, the `auto` Run of the round before it whose `cancel`
record says `reopen` is shown as stopped on the spec, and the reopened step names that workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from orchestrator.application.rules import initiative_transitions as rules
from orchestrator.application.use_cases.initiative_view_types import Loaded
from orchestrator.domain.entities.run import Run


@dataclass(frozen=True)
class ReopenMark:
    auto_index: int
    workflow: str
    step: str
    branch: Literal["created", "attached"]


def _latest_spec(loaded: Loaded) -> Run | None:
    sequence = loaded.initiative.sequence
    spec = [i for i, entry in enumerate(sequence.workflows) if rules.is_spec(entry)]
    runs = [r for r in loaded.runs if r.initiative_position in spec]
    return max(runs, key=lambda r: r.created_at, default=None)


def reopen_mark(loaded: Loaded) -> ReopenMark | None:
    """The reopen that cancelled an `auto` Run, while its round's spec Run is not `done`."""
    spec = _latest_spec(loaded)
    if spec is None or spec.status == "done" or spec.initiative_round is None:
        return None
    workflows = loaded.initiative.sequence.workflows
    for run in sorted(loaded.runs, key=lambda r: r.created_at):
        index = run.initiative_position
        if index is None or workflows[index].type != rules.AUTO:
            continue
        if run.initiative_round != spec.initiative_round - 1:
            continue
        for record in loaded.records.get(run.id, []):
            if record.event == "cancel" and record.payload.get("reason") == rules.REOPEN_REASON:
                return ReopenMark(
                    auto_index=index,
                    workflow=workflows[index].workflow,
                    step=str(record.payload.get("step")),
                    branch=cast(Literal["created", "attached"], record.payload.get("branch")),
                )
    return None
