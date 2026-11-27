"""Reopen each conversation an upgrade cancelled, at the next start (SPEC CAP-5, AD-30).

An initiative already reopened has a later Run, so a second start finds nothing to do.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from orchestrator.application.use_cases.initiative_reopen import reopen_initiative
from orchestrator.application.use_cases.initiatives import InitiativePorts
from orchestrator.application.use_cases.upgrade_prepare import UPGRADE_REASON
from orchestrator.domain.entities.initiative import Initiative

log = structlog.get_logger(__name__)

UPGRADE_TURN = (
    "instance upgraded: this step reopens here. The step file on this branch holds what was "
    "written; continue the conversation where it stopped."
)


def _step_to_reopen(ports: InitiativePorts, initiative: Initiative) -> str | None:
    runs = ports.runs.list_for_initiative(initiative.id)
    latest = max(runs, key=lambda run: (run.created_at, run.id), default=None)
    if latest is None or latest.status != "cancelled":
        return None
    records = ports.signals.signal.writers.records.list_for_run(latest.id)
    cancels = [record for record in records if record.event == "cancel"]
    if not cancels:
        return None
    payload = cancels[-1].payload or {}
    step = payload.get("step")
    if payload.get("reason") != UPGRADE_REASON or not isinstance(step, str) or not step:
        return None
    return step


def reopen_after_upgrade(ports: InitiativePorts) -> tuple[UUID, ...]:
    """Reopen every open initiative whose latest Run an upgrade cancelled; return their ids."""
    reopened: list[UUID] = []
    for initiative in ports.initiatives.list():
        if initiative.cancelled_at is not None or initiative.pr_merged_at is not None:
            continue
        step = _step_to_reopen(ports, initiative)
        if step is None:
            continue
        try:
            reopen_initiative(ports, initiative.id, step, UPGRADE_TURN)
        except Exception as exc:
            log.warning("upgrade_reopen_failed", initiative_id=str(initiative.id), error=str(exc))
            continue
        reopened.append(initiative.id)
    return tuple(reopened)
