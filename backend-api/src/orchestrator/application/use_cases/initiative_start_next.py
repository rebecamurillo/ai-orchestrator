"""Force the next conversation step of an initiative (SPEC CAP-5; AD-13 amended).

The gate, the merge and the build are never forced: only a `conversation` step that follows the
parked one, and that the round names when it names any, is skipped.
"""

from __future__ import annotations

from uuid import UUID

from orchestrator.application.rules import conversation
from orchestrator.application.rules.signals import row_at
from orchestrator.application.use_cases.initiatives import InitiativePorts
from orchestrator.application.use_cases.signals import handle_signal
from orchestrator.domain.entities.initiative import FrozenWorkflow, Initiative
from orchestrator.domain.entities.project_package import StepDecl
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.values import Signal

NO_CONVERSATION = "no conversation step is open"
NOT_FORCEABLE = (
    "start-next refused: the next step is not a conversation step; "
    "the gate, the merge and the build are never forced"
)


def _next_step(workflow: FrozenWorkflow, step: str) -> StepDecl | None:
    ids = [decl.id for decl in workflow.steps]
    if step not in ids or ids.index(step) + 1 >= len(ids):
        return None
    return workflow.steps[ids.index(step) + 1]


def _open_conversation(ports: InitiativePorts, initiative: Initiative) -> tuple[Run, int, str]:
    runs = ports.runs.list_for_initiative(initiative.id)
    run = runs[-1] if runs else None
    if run is None or run.status != "needs_you" or run.park_kind != "conversation":
        raise Conflict(NO_CONVERSATION)
    if run.initiative_position is None:
        raise Conflict(NO_CONVERSATION)
    row = row_at(ports.signals.signal.writers.steps.list_for_run(run.id), run.park_path)
    if row is None:
        raise Conflict(NO_CONVERSATION)
    return run, run.initiative_position, str(row.with_resolved.get(conversation.STEP_KEY) or "")


def _refuse_unforceable(initiative: Initiative, run: Run, position: int, step: str) -> None:
    following = _next_step(initiative.sequence.workflows[position], step)
    named = conversation.round_list(run.inputs)
    if (
        following is None
        or following.kind != "conversation"
        or (named and following.id not in named)
    ):
        raise Conflict(NOT_FORCEABLE)


def start_next(ports: InitiativePorts, initiative_id: UUID, park_seq: int) -> Initiative:
    """Skip the parked conversation step, forced, at the stop the operator saw."""
    initiative = ports.initiatives.get_for_update(initiative_id)
    if initiative is None:
        raise NotFound(f"no initiative {initiative_id}")
    try:
        run, position, step = _open_conversation(ports, initiative)
        _refuse_unforceable(initiative, run, position, step)
        handle_signal(
            ports.signals,
            run.id,
            Signal(kind="skip_step", stop=park_seq, payload={"forced": True}),
        )
    except Exception:
        ports.uow.rollback()
        raise
    ports.uow.commit()
    return initiative
