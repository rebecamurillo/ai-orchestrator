"""The initiative pull-request check: an initiative is done once its build's pull requests merged.

Writes `pr_merged_at` and nothing else (AD-36 "Writers"); the status itself stays computed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

import structlog

from orchestrator.application.rules.initiative_status import build_index
from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.initiative_runs import InitiativeRunReads
from orchestrator.domain.ports.initiatives import InitiativeRepository
from orchestrator.domain.ports.pull_requests import PullRequests
from orchestrator.domain.ports.unit_of_work import UnitOfWork

log = structlog.get_logger(__name__)

#: The inverse of the `pr.link` step's compare URL.
COMPARE_URL_PATTERN = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/compare/(?P<base>.+?)\.\.\.(?P<branch>.+)$"
)
UNREADABLE = "GitHub unreadable"
UNPARSABLE = "unparsable compare url"

PullRequestKey = tuple[str, str, str]


@dataclass(frozen=True)
class InitiativePrCheckPorts:
    uow: UnitOfWork
    initiatives: InitiativeRepository
    runs: InitiativeRunReads
    pull_requests: PullRequests
    clock: Clock


def run_initiative_pr_check(ports: InitiativePrCheckPorts) -> tuple[UUID, ...]:
    """The ids of the initiatives marked merged by this pass."""
    with ports.uow:
        candidates = [
            (initiative.id, keys)
            for initiative in ports.initiatives.list()
            if initiative.is_open and (keys := _build_keys(ports, initiative))
        ]
    return tuple(
        initiative_id
        for initiative_id, keys in candidates
        if _all_merged(ports, initiative_id, keys) and _mark_merged(ports, initiative_id)
    )


def _build_keys(ports: InitiativePrCheckPorts, initiative: Initiative) -> list[PullRequestKey]:
    index = build_index(initiative)
    runs = [
        run
        for run in ports.runs.list_for_initiative(initiative.id)
        if index is not None and run.initiative_position == index
    ]
    latest = max(runs, key=lambda run: run.created_at, default=None)
    if latest is None or latest.status != "done":
        return []
    keys: list[PullRequestKey] = []
    for url in latest.compare_urls:
        found = COMPARE_URL_PATTERN.match(url)
        if found is None:
            log.warning(
                "initiative_pr_check",
                reason=UNPARSABLE,
                url=url,
                initiative_id=str(initiative.id),
            )
            continue
        keys.append((found["owner"], found["repo"], found["branch"]))
    return keys


def _all_merged(
    ports: InitiativePrCheckPorts, initiative_id: UUID, keys: list[PullRequestKey]
) -> bool:
    answers = [ports.pull_requests.merged(*key) for key in keys]
    if None in answers:
        log.warning("initiative_pr_check", reason=UNREADABLE, initiative_id=str(initiative_id))
    return all(answer is True for answer in answers)


def _mark_merged(ports: InitiativePrCheckPorts, initiative_id: UUID) -> bool:
    with ports.uow:
        current = ports.initiatives.get_for_update(initiative_id)
        if current is None or not current.is_open:
            return False
        ports.initiatives.update(current.model_copy(update={"pr_merged_at": ports.clock.now()}))
        ports.uow.commit()
    return True
