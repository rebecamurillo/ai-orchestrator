"""One planned row of a Run: what the planner wrote, and where execution got to (AD-7).

`seq` orders and `path` names, and both are unique per Run — the two unique indexes on the
`step_run` table are what make a plan a list rather than a bag. `seq` is dense, so the
walker's "the next row" is the next number and never a scan for a gap.

`kind` is a plain `str` because `application/steps/__init__.py::KIND_META` is the only
enumeration of kinds (AD-9) and `domain/` may not import `application/` (AD-2). `gate` is
the domain `Gate`, four tokens: the planner records `unvalidated` for a step whose Template
declared no gate, and that row never renders green (NFR-2).

`frame` and `story_id` are filled by the planner (4.2) and read by Epic 6's skip signals —
`skip_story` re-queues by frame, not by row — and they are here now so that story needs no
second migration. `retry_count` and `redispatch_count` are the bounded counters AD-9's
re-execution rules read; nothing here increments them, `apply_step_result` does.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.domain.statuses import Gate, StepStatus


class StepRun(BaseModel):
    """One row of a Run's plan, as it is stored."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    run_id: UUID
    #: Dense and unique per Run: the order the walker executes in.
    seq: int
    #: Unique per Run: the dotted path the plan gave this row, e.g. `steps[3].stories[0]`.
    path: str
    label: str
    kind: str
    gate: Gate
    status: StepStatus
    #: The sentence the Operator reads on the row; `None` while nothing has happened to it.
    reason: str | None = None
    #: The step's `with:` block after template substitution, read whole by its executor.
    with_resolved: dict[str, Any] = Field(default_factory=dict)
    retry_count: int = 0
    redispatch_count: int = 0
    #: The innermost `…stories[n]` / `epics[n]` prefix of `path`, or `None` outside a frame.
    frame: str | None = None
    story_id: str | None = None
