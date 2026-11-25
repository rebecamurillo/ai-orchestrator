"""The initiative adapters' row mapping and the models' declarations (AD-36)."""

from __future__ import annotations

from sqlalchemy import Integer, Text

from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models.initiative import InitiativeAdvanceRow, InitiativeRow
from orchestrator.infrastructure.db.repositories import initiatives as module
from orchestrator.infrastructure.db.repositories import runs as runs_module
from tests.unit.initiative_fixtures import AT, a_run, an_initiative

INITIATIVE = Base.metadata.tables["initiative"]
ADVANCE = Base.metadata.tables["initiative_advance"]
RUN = Base.metadata.tables["run"]


def test_an_initiative_round_trips_through_its_row() -> None:
    initiative = an_initiative(
        cancelled_at=AT, branch_cleanup_error="x", pr_merged_at=AT, last_opened_at=AT, round=3
    )
    row = InitiativeRow(**module.row_values(initiative), updated_at=AT)

    assert module.to_entity(row) == initiative.model_copy(update={"updated_at": AT})
    assert module.to_entity(row).sequence == initiative.sequence


def test_an_unflushed_row_reads_round_one() -> None:
    row = InitiativeRow(**module.row_values(an_initiative()))
    row.round = None  # type: ignore[assignment]

    assert module.to_entity(row).round == 1


def test_updated_at_is_the_databases() -> None:
    assert "updated_at" not in module.row_values(an_initiative())


def test_an_advance_round_trips_through_its_row() -> None:
    advance = InitiativeAdvance(
        id=new_id(),
        initiative_id=new_id(),
        from_run_id=new_id(),
        round=2,
        position=1,
        blocked_reason="why",
        consumed_at=AT,
    )

    row = InitiativeAdvanceRow(**module.advance_row_values(advance))

    assert module.advance_to_entity(row) == advance


def test_the_slug_index_is_partial_unique() -> None:
    indexes = {index.name: index for index in INITIATIVE.indexes}

    index = indexes["uq_initiative_repository_slug_open"]
    assert index.unique is True
    assert [c.name for c in index.columns] == ["repository_id", "slug"]
    assert str(index.dialect_options["postgresql"]["where"]) == "cancelled_at IS NULL"


def test_the_advance_key_is_unique() -> None:
    uniques = [
        [c.name for c in constraint.columns]
        for constraint in ADVANCE.constraints
        if constraint.name == "uq_initiative_advance_initiative_id_round_position"
    ]

    assert uniques == [["initiative_id", "round", "position"]]


def test_nullable_columns() -> None:
    assert {c.name for c in INITIATIVE.columns if c.nullable} == {
        "cancelled_at",
        "branch_cleanup_error",
        "pr_merged_at",
        "last_opened_at",
    }
    assert {c.name for c in ADVANCE.columns if c.nullable} == {"blocked_reason", "consumed_at"}
    assert isinstance(INITIATIVE.columns["round"].type, Integer)
    assert isinstance(INITIATIVE.columns["slug"].type, Text)


def test_the_foreign_keys_point_one_way() -> None:
    def targets(table: object) -> set[str]:
        return {fk.target_fullname for fk in table.foreign_keys}  # type: ignore[attr-defined]

    assert targets(INITIATIVE) == {"project.id", "repository.id"}
    assert targets(ADVANCE) == {"initiative.id", "run.id"}
    assert "initiative.id" in targets(RUN)


def test_the_run_adapter_maps_the_three_keys_both_ways() -> None:
    run = a_run(initiative_id=new_id(), initiative_round=2, initiative_position=1)

    values = runs_module.row_values(run)

    assert (values["initiative_id"], values["initiative_round"], values["initiative_position"]) == (
        run.initiative_id,
        2,
        1,
    )
    assert "initiative_id" in runs_module.MUTABLE_COLUMNS
