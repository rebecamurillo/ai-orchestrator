"""`Initiative`, `InitiativeAdvance`, `InitiativeKey` and the Run's initiative keys (AD-36)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.domain.entities.initiative import InitiativeKey
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.domain.ids import new_id
from tests.unit.initiative_fixtures import AT, a_run, an_initiative


def test_defaults() -> None:
    initiative = an_initiative()

    assert initiative.round == 1
    assert initiative.last_opened_at is None
    assert initiative.cancelled_at is None


def test_frozen() -> None:
    with pytest.raises(ValidationError):
        an_initiative().slug = "other"  # type: ignore[misc]


def test_is_open_only_when_neither_cancelled_nor_merged() -> None:
    assert an_initiative().is_open
    assert not an_initiative(cancelled_at=AT).is_open
    assert not an_initiative(pr_merged_at=AT).is_open


def test_keys_compare_by_value() -> None:
    i = new_id()

    assert InitiativeKey(initiative_id=i, round=1, position=0) == InitiativeKey(
        initiative_id=i, round=1, position=0
    )
    assert InitiativeKey(initiative_id=i, round=1, position=0) != InitiativeKey(
        initiative_id=i, round=2, position=0
    )


def test_advance_defaults() -> None:
    advance = InitiativeAdvance(
        id=new_id(), initiative_id=new_id(), from_run_id=new_id(), round=1, position=0
    )

    assert advance.blocked_reason is None
    assert advance.consumed_at is None


def test_a_run_has_no_initiative_keys_by_default() -> None:
    run = a_run()

    assert (run.initiative_id, run.initiative_round, run.initiative_position) == (None,) * 3
