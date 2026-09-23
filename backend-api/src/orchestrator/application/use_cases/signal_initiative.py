"""`signal_initiative` (AD-13, multi-repo initiative S8): the one signal surface above a
single Run.

`POST /initiatives/{slug}/signals` admits exactly one kind, `cancel`, and fans it over the
initiative's own member Runs — every Run `list_by_initiative(slug)` answers, no second
source (`initiative_view.py`'s own rule: "there is no initiative table"). Each fan-out is an
ordinary `signal_run(ports, run_id, Signal(kind="cancel"))` (`signal_run.py`): no new
transition, no new park kind, no second writer of Run status (AD-8) — this module decides
*which* member Runs to call it on and in what order, and nothing else.

**Dependents first.** A cancelled predecessor whose dependent is still queued would leave
that dependent parked `dependency` forever (nothing ever resolves it once its predecessor
never reaches `done`); cancelling the dependent first, then its predecessor, leaves nothing
behind. The order is an ordinary reverse-topological sort of the `after_run_ids` edges among
the members being signalled: a member listing another member's id in its own `after_run_ids`
depends on it, so the edge runs predecessor → dependent, and dependents-first is that graph's
own edges reversed. Ties — members with no ordering between them — are broken by reverse
creation order: `list_by_initiative` answers newest first (the convention every Run list
shares), so reversing it once gives creation order (also AD-12's own dispatch order, since a
dependent's `after_run_ids` can only name a Run dispatch already created); the topological
sort below reads its *ready* set in that creation order and only reverses the whole result at
the end, which is what hands the ties their tie-break "for free" rather than a second rule.

**Which members are signalled.** `cancel`'s own row in AD-13's table (`rules/signals.py::
VALID["cancel"]`) is read directly rather than re-stated: `run_statuses` is every non-terminal
status and `park_kinds` is every park kind, so the one gate a member has to clear is not being
terminal already — reading the table rather than hardcoding that equivalence means a future
change to cancel's own row (a park kind it stops admitting, say) is picked up here without
touching this module. A member that fails the gate is skipped, not attempted and caught:
`signal_run` itself would refuse a terminal Run with `Conflict`, but a fan-out is not the
place a single member's own refusal belongs (the story is "cancel every non-terminal member";
a terminal one already did what cancel asks).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from orchestrator.application.rules.signals import VALID
from orchestrator.application.use_cases.signal_run import SignalPorts, signal_run
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Invalid, NotFound
from orchestrator.domain.statuses import SignalKind
from orchestrator.domain.values import Signal

#: The one kind this surface admits (AD-13's own sentence: "it admits `cancel`").
CANCEL: SignalKind = "cancel"

#: What every kind other than `cancel` is refused with — `signal_run.py::_check_mode`'s own
#: `Invalid(f"unknown mode: {mode}")` is this module's precedent for an unknown token on a
#: signal surface: a 422, not a 409, because no Run state makes any other kind valid here.
UNSUPPORTED_KIND = "initiative signal {kind!r} not supported: only 'cancel' is"


@dataclass(frozen=True)
class SignalInitiativeOutcome:
    """What the endpoint reports: the member Runs signalled, and the ones already terminal."""

    signalled: tuple[UUID, ...]
    skipped: tuple[UUID, ...]


def signal_initiative(ports: SignalPorts, slug: str, kind: str) -> SignalInitiativeOutcome:
    """Cancel every non-terminal member Run of one initiative, dependents first."""
    if kind != CANCEL:
        raise Invalid(UNSUPPORTED_KIND.format(kind=kind))
    members = ports.writers.runs.list_by_initiative(slug)
    if not members:
        raise NotFound(f"no initiative {slug!r}")
    cancellable = VALID[CANCEL].run_statuses
    signalled: list[UUID] = []
    skipped: list[UUID] = []
    for run in _reverse_topological(members):
        if run.status not in cancellable:
            skipped.append(run.id)
            continue
        signal_run(ports, run.id, Signal(kind=CANCEL, payload={}))
        signalled.append(run.id)
    return SignalInitiativeOutcome(signalled=tuple(signalled), skipped=tuple(skipped))


def _reverse_topological(members: Sequence[Run]) -> list[Run]:
    """Dependents before predecessors, ties by reverse creation order (module docstring).

    `members` arrives newest first (`list_by_initiative`'s own convention); reversing it once
    gives creation order, a valid topological order on its own (AD-12 dispatches in exactly
    that order) that this still re-derives from `after_run_ids` rather than trusting: at each
    step the earliest-created member whose own dependencies (among these members) are already
    placed is appended next, which is `oldest_first`'s order read left to right. Reversing
    that whole result once at the end is what turns "predecessors first" into "dependents
    first" and "earliest creation" ties into "most recent creation" ties, together.
    """
    oldest_first = list(reversed(members))
    member_ids = {run.id for run in oldest_first}
    placed: set[UUID] = set()
    ordered: list[Run] = []
    pending = list(oldest_first)
    while pending:
        run = next(
            candidate
            for candidate in pending
            if all(dep in placed for dep in candidate.after_run_ids if dep in member_ids)
        )
        ordered.append(run)
        placed.add(run.id)
        pending.remove(run)
    return list(reversed(ordered))
