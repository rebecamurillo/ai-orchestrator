"""The gate verdict columns of `attempt` round-trip (epic 8 story 2, AC8)."""

from __future__ import annotations

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.models.run import AttemptRow
from orchestrator.infrastructure.db.repositories import attempts as attempts_module

VERDICT = ("verdict_word", "verdict_fields", "verdict_text")


def an_attempt(**over: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "step_run_id": new_id(),
        "n": 1,
        "status": "done",
    }
    fields.update(over)
    return Attempt(**fields)  # type: ignore[arg-type]


def test_an_attempt_carries_no_verdict_by_default() -> None:
    attempt = an_attempt()

    assert (attempt.verdict_word, attempt.verdict_fields, attempt.verdict_text) == (None,) * 3


def test_a_verdict_round_trips_through_its_row() -> None:
    attempt = an_attempt(
        verdict_word="fail", verdict_fields={"owners": ["ux", "tech"]}, verdict_text="- a\n- b"
    )

    values = attempts_module.row_values(attempt)
    row = AttemptRow(**values)

    assert (row.verdict_word, row.verdict_fields, row.verdict_text) == (
        "fail",
        {"owners": ["ux", "tech"]},
        "- a\n- b",
    )
    assert attempts_module.to_entity(row) == attempt


def test_an_attempt_without_a_verdict_round_trips_nulls() -> None:
    attempt = an_attempt()

    row = AttemptRow(**attempts_module.row_values(attempt))

    assert (row.verdict_word, row.verdict_fields, row.verdict_text) == (None,) * 3
    assert attempts_module.to_entity(row) == attempt


def test_mark_finished_writes_the_three_columns() -> None:
    for name in VERDICT:
        assert name in attempts_module.FINISHED_COLUMNS
        assert name not in attempts_module.STARTED_COLUMNS
