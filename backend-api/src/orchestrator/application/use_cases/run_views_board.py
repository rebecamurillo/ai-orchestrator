"""The Board (SPEC CAP-12, CAP-14): one card per Run, in its column.

Moved out of `run_views.py` on line count; `run_views.py` re-exports `board_view`. Reads
through `RunReadPorts` (see that module's docstring for why not `RunViewPorts`).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from orchestrator.application.rules.initiative_status import RunFacts
from orchestrator.application.rules.signals import row_at
from orchestrator.application.steps import CONVERSATION_KIND
from orchestrator.application.use_cases.initiative_facts import (
    initiative_tag,
    run_facts,
    template_type_of,
)
from orchestrator.application.use_cases.run_read_ports import RunReadPorts
from orchestrator.application.use_cases.run_view_types import (
    BoardColumns,
    BoardCounts,
    BoardView,
    Card,
)
from orchestrator.application.use_cases.run_views_alert import run_token
from orchestrator.application.use_cases.run_views_summary import progress
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun

__all__ = ["board_current_step_label", "board_view"]


def board_view(ports: RunReadPorts, *, project_id: UUID | None, now: datetime) -> BoardView:
    """Every Run, one card each, in its column — `cancelled` files under `failed` (CAP-14)."""
    memo: dict[tuple[str, int], str | None] = {}
    cards = [
        _card(ports, run, now=now, memo=memo) for run in ports.runs.list(project_id=project_id)
    ]
    columns = BoardColumns(
        queued=[card for card in cards if card.status == "queued"],
        running=[card for card in cards if _in_running(card)],
        needs_you=[card for card in cards if _in_needs_you(card)],
        done=[card for card in cards if card.status == "done"],
        failed=[card for card in cards if card.status in ("failed", "cancelled")],
    )
    counts = BoardCounts(
        running=len(columns.running),
        queued=len(columns.queued),
        needs_you=len(columns.needs_you),
    )
    return BoardView(columns=columns, counts=counts, generated_at=now)


def _in_needs_you(card: Card) -> bool:
    """Only attention `blocked`, or none read, keeps a `needs_you` Run in Needs-you."""
    return card.status == "needs_you" and card.attention in ("blocked", None)


def _in_running(card: Card) -> bool:
    return card.status == "running" or (card.status == "needs_you" and not _in_needs_you(card))


def _card(
    ports: RunReadPorts, run: Run, *, now: datetime, memo: dict[tuple[str, int], str | None]
) -> Card:
    steps = ports.steps.list_for_run(run.id) if ports.steps is not None else []
    facts = _facts(ports, run, steps)
    initiative = (
        ports.initiatives.get(run.initiative_id)
        if ports.initiatives is not None and run.initiative_id is not None
        else None
    )
    project = ports.projects.get(run.project_id) if ports.projects is not None else None
    repository = (
        ports.repositories.get(run.repository_id) if ports.repositories is not None else None
    )
    return Card(
        id=run.id,
        token=run_token(run),
        status=run.status,
        park_kind=run.park_kind,
        branch=str(run.inputs.get("base_branch", "")),
        project_name=project.name if project is not None else "",
        repository_slug=repository.slug if repository is not None else "",
        current_step_label=_board_current_step_label(run, steps),
        harness=run.inputs.get("harness"),
        template=run.template_name,
        version=run.template_version,
        progress=progress(run, steps),
        kind_label=_kind_label(run, steps),
        age_seconds=(now - run.created_at).total_seconds(),
        needs_you_since=_needs_you_since(ports, run) if run.status == "needs_you" else None,
        label=run.label,
        label_set_by_operator=run.label_set_by_operator,
        initiative=None
        if initiative is None
        else initiative_tag(initiative, run, None if facts is None else facts.step),
        attention=None if facts is None else facts.attention,
        template_type=template_type_of(
            ports.templates, run.template_name, run.template_version, memo
        ),
    )


def _facts(ports: RunReadPorts, run: Run, steps: Sequence[StepRun]) -> RunFacts | None:
    """The Run's attention facts, or `None` where no attempt read was wired."""
    if ports.attempts is None:
        return None
    # Attention reads the parked row's turns and file only for a conversation park; any
    # other card skips both reads, which the Board would otherwise repeat for every Run.
    if run.status != "needs_you" or run.park_kind != CONVERSATION_KIND:
        return run_facts(run, steps, (), None)
    parked = row_at(steps, run.park_path)
    attempts = [] if parked is None else ports.attempts.list_for_row(parked.id)
    return run_facts(run, steps, attempts, ports.workspace)


def _kind_label(run: Run, steps: Sequence[StepRun]) -> str | None:
    """What a Card shows where it has no epic/story progress to show (SPEC CAP-12): the
    Run's own Template name, the same identity `graph.py::_run_node` puts on the root node.

    Was a two-entry lookup table whose keys were shipped Template names, which both named
    them in product code and left every other Template with a blank segment (Operator
    decision 2026-09-30: no template name hardcoded in product code). `None` once there *is*
    progress, because the two are alternatives on the card and never both.
    """
    return None if progress(run, steps) is not None else run.template_name


def _board_current_step_label(run: Run, steps: Sequence[StepRun]) -> str:
    """The running row's label, else the park row's, else the last `done` row's (CAP-12)."""
    running = next((row for row in steps if row.status == "running"), None)
    if running is not None:
        return running.label
    parked = row_at(steps, run.park_path)
    if parked is not None:
        return parked.label
    done = [row for row in steps if row.status == "done"]
    return done[-1].label if done else ""


def _needs_you_since(ports: RunReadPorts, run: Run) -> datetime | None:
    """The `.at` of the most recent gate record matching `run.park_kind` — the only durable
    record of when a Run parked (`Run` itself carries no such timestamp)."""
    if ports.gate_records is None:
        return None
    records = ports.gate_records.list_for_run(run.id)
    matching = [record for record in records if record.event == run.park_kind]
    return matching[-1].at if matching else None


board_current_step_label = _board_current_step_label
