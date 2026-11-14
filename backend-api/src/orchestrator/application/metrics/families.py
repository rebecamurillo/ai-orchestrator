"""Role families: the roles a template may spell differently, summed so two Runs line up.

A family cell is the sum of its roles' values at one scope type and one source; sums never cross
scope types and a missing figure never becomes 0 (it makes the cell `partial`, or reads its
word). `as declared: …` roles are never grouped. A Run without any role of the family reads
`no such step in this template`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from uuid import UUID

from orchestrator.application.metrics.values import NO_SUCH_STEP, PARTIAL
from orchestrator.application.rules.frames import story_frame
from orchestrator.domain.entities.metric_results import StoredMetricValue
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.catalogue import CatalogueEntry

ORCHESTRATE = "orchestrate"
FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("story work", ("plan", "implement", "review", ORCHESTRATE)),
    ("verification", ("verify", "e2e-gen", "e2e")),
    ("gates", ("spec-gate",)),
    ("retro", ("retro",)),
    ("deterministic", ("deterministic",)),
    ("senior", ("senior",)),
    ("chat", ("chat",)),
)
InStory = Literal["all", "none", "mixed"]


@dataclass(frozen=True)
class FamilyCell:
    value_num: Decimal | None
    missing: str | None
    roles: tuple[str, ...]


@dataclass(frozen=True)
class FamilyResult:
    family: str
    source: str | None
    cells: dict[UUID, FamilyCell]
    step_structure_differs: bool


def family_applies(entry: CatalogueEntry) -> bool:
    """Only role-scoped metrics that can be added along a partition are grouped."""
    return "role" in entry.scopes and entry.additive is not False


def orchestrate_in_story(rows: Sequence[StepRun]) -> InStory:
    """Whether the Run's `orchestrate` step rows lie in a story frame: all, none, or mixed."""
    inside = [story_frame(row.path) is not None for row in rows if row.role == ORCHESTRATE]
    if all(inside):
        return "all" if inside else "none"
    return "mixed" if any(inside) else "none"


def _fold(parts: Sequence[tuple[Decimal | None, str | None]]) -> tuple[Decimal | None, str | None]:
    figures = [figure for figure, _ in parts if figure is not None]
    if not figures:
        return None, parts[0][1]
    partial = len(figures) < len(parts) or any(word == PARTIAL for _, word in parts)
    return sum(figures, Decimal(0)), PARTIAL if partial else None


def _part(rows: Sequence[StoredMetricValue]) -> tuple[Decimal | None, str | None]:
    return _fold([(row.value_num, row.missing) for row in rows])


def _role_rows(
    values: Sequence[StoredMetricValue], role: str, source: str | None, mode: InStory
) -> list[StoredMetricValue]:
    if role == ORCHESTRATE and mode != "all":
        if mode == "none":
            return []
        return [
            v
            for v in values
            if v.scope_type == "attempt"
            and v.role == role
            and v.source == source
            and story_frame(v.scope_key.split("#")[0]) is not None
        ]
    return [
        v for v in values if v.scope_type == "role" and v.scope_key == role and v.source == source
    ]


def _cell(
    values: Sequence[StoredMetricValue], roles: Iterable[str], source: str | None, mode: InStory
) -> FamilyCell | None:
    found = [(role, _role_rows(values, role, source, mode)) for role in roles]
    present = [(role, rows) for role, rows in found if rows]
    if not present:
        return None
    figure, word = _fold([_part(rows) for _, rows in present])
    return FamilyCell(figure, word, tuple(role for role, _ in present))


def family_results(
    values_by_run: Mapping[UUID, Sequence[StoredMetricValue]], modes: Mapping[UUID, InStory]
) -> list[FamilyResult]:
    """Every family some Run has, per source, in family order."""
    sources = sorted(
        {v.source for values in values_by_run.values() for v in values if v.scope_type == "role"}
        | {v.source for values in values_by_run.values() for v in values if v.role == ORCHESTRATE},
        key=lambda s: s or "",
    )
    results: list[FamilyResult] = []
    for family, roles in FAMILIES:
        for source in sources:
            found = {
                run_id: _cell(values, roles, source, modes[run_id])
                for run_id, values in values_by_run.items()
            }
            cells = {run_id: cell for run_id, cell in found.items() if cell is not None}
            if not cells:
                continue
            absent = FamilyCell(None, NO_SUCH_STEP, ())
            role_sets = {cell.roles for cell in cells.values()}
            results.append(
                FamilyResult(
                    family,
                    source,
                    {run_id: found[run_id] or absent for run_id in values_by_run},
                    len(role_sets) > 1,
                )
            )
    return results
