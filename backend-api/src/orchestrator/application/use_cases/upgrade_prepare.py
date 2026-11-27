"""Cancel the conversations that wait for the operator before an upgrade (SPEC CAP-3, AD-30).

All or nothing: the hold is read under its shared lock, every interactive initiative Run is
classified, a refusal comes before any signal, and the unit of work commits last so a release of
the hold cannot interleave with the cancels.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from orchestrator.application.rules.signals import row_at
from orchestrator.application.use_cases.initiative_facts import conversation_step
from orchestrator.application.use_cases.initiatives import InitiativePorts
from orchestrator.application.use_cases.instance_hold import hold_active
from orchestrator.application.use_cases.signals import handle_signal
from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ports.instance_hold import InstanceHoldRepository
from orchestrator.domain.statuses import TERMINAL_RUN
from orchestrator.domain.values import Signal

UPGRADE_REASON = "upgrade"
NO_HOLD = "no instance hold; take one with POST /api/v1/instance/hold first"
REFUSED = "upgrade-prepare refused: interactive Runs not parked on a conversation: {runs}"


@dataclass(frozen=True)
class PreparedConversation:
    run_id: UUID
    initiative_id: UUID
    step: str


@dataclass(frozen=True)
class UpgradePorts:
    """`holds` shares the session of `initiative.uow`."""

    initiative: InitiativePorts
    holds: InstanceHoldRepository


def _interactive_runs(ports: InitiativePorts, initiative: Initiative) -> list[Run]:
    workflows = initiative.sequence.workflows
    return [
        run
        for run in ports.runs.list_for_initiative(initiative.id)
        if run.status not in TERMINAL_RUN
        and run.initiative_position is not None
        and run.initiative_position < len(workflows)
        and workflows[run.initiative_position].type == "interactive"
    ]


def _parked_step(ports: InitiativePorts, run: Run) -> str | None:
    """The step a conversation-parked Run waits on, `None` for any other state."""
    if run.status != "needs_you" or run.park_kind != "conversation":
        return None
    row = row_at(ports.signals.signal.writers.steps.list_for_run(run.id), run.park_path)
    return (conversation_step(row) if row is not None else "") or None


def _classify(ports: InitiativePorts) -> tuple[list[tuple[Run, str]], list[Run]]:
    parked: list[tuple[Run, str]] = []
    refused: list[Run] = []
    for initiative in ports.initiatives.list():
        for run in _interactive_runs(ports, initiative):
            step = _parked_step(ports, run)
            if step is None:
                refused.append(run)
            else:
                parked.append((run, step))
    parked.sort(key=lambda pair: (pair[0].created_at, pair[0].id))
    refused.sort(key=lambda run: (run.created_at, run.id))
    return parked, refused


def prepare_upgrade(ports: UpgradePorts) -> tuple[PreparedConversation, ...]:
    """Cancel each parked initiative conversation with the reason `upgrade`; list them."""
    base = ports.initiative
    try:
        if not hold_active(ports.holds, base.clock.now()):
            raise Conflict(NO_HOLD)
        parked, refused = _classify(base)
        if refused:
            names = ", ".join(f"{r.id} ({r.status}/{r.park_kind or '-'})" for r in refused)
            raise Conflict(REFUSED.format(runs=names))
        done: list[PreparedConversation] = []
        for run, step in parked:
            signal = Signal(kind="cancel", payload={"reason": UPGRADE_REASON, "step": step})
            try:
                handle_signal(base.signals, run.id, signal)
            except Conflict:
                continue  # ended by itself meanwhile
            assert run.initiative_id is not None
            done.append(PreparedConversation(run.id, run.initiative_id, step))
    except Exception:
        base.uow.rollback()
        raise
    base.uow.commit()
    return tuple(done)
