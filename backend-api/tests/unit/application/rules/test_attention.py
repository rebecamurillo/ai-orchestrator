"""Attention of a Run (epic 7 story 2, SPEC CAP-2; AD-36 "Attention")."""

from __future__ import annotations

from typing import Any

from orchestrator.application.rules.attention import attention
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from tests.unit.initiative_fixtures import a_run
from tests.unit.step_fixtures import a_row

PATH = "ux"
NOT_CLOSED = "step not closed · PRD.md has status draft, the done content is status final"


def _parked(**overrides: Any) -> Any:
    values: dict[str, Any] = {
        "status": "needs_you",
        "park_kind": "conversation",
        "park_path": PATH,
        "park_reason": "her turn",
    }
    values.update(overrides)
    return a_run(**values)


def _turn(row: StepRun, n: int, status: str, role: str = "session") -> Attempt:
    return Attempt(
        id=new_id(), run_id=row.run_id, step_run_id=row.id, n=n, status=status, role=role
    )  # type: ignore[arg-type]


def _row(path: str = PATH, **resolved: Any) -> StepRun:
    return a_row(kind="conversation", with_resolved=resolved, path=path)


def test_not_needs_you_has_no_attention() -> None:
    assert attention(a_run(status="running"), [], [], step_word=None) is None


def test_other_stop_is_blocked() -> None:
    run = _parked(park_kind="blocked")
    assert attention(run, [], [], step_word=None) == "blocked"


def test_queued_while_another_runs() -> None:
    row = _row()
    turns = [_turn(row, 1, "running"), _turn(row, 2, "queued")]
    assert attention(_parked(), [row], turns, step_word=None) == "queued"


def test_running_is_answering() -> None:
    row = _row()
    assert attention(_parked(), [row], [_turn(row, 1, "running")], step_word=None) == "answering"


def test_queued_alone_falls_through_to_your_turn() -> None:
    row = _row()
    turns = [_turn(row, 1, "done"), _turn(row, 2, "queued")]
    assert attention(_parked(), [row], turns, step_word=None) == "your_turn"


def test_last_ended_error_is_blocked() -> None:
    row = _row()
    turns = [_turn(row, 1, "done"), _turn(row, 2, "error")]
    assert attention(_parked(), [row], turns, step_word=None) == "blocked"


def test_earlier_error_with_last_done_is_your_turn() -> None:
    row = _row()
    turns = [_turn(row, 2, "done"), _turn(row, 1, "error")]
    assert attention(_parked(), [row], turns, step_word=None) == "your_turn"


def test_step_word_in_expect_blocked() -> None:
    row = _row(expect={"blocked": ["stuck", "help"]})
    assert attention(_parked(), [row], [_turn(row, 1, "done")], step_word="help") == "blocked"


def test_step_word_not_in_expect_blocked() -> None:
    row = _row(expect={"blocked": ["stuck"]})
    assert attention(_parked(), [row], [_turn(row, 1, "done")], step_word="final") == "your_turn"


def test_expect_not_a_mapping_is_tolerated() -> None:
    row = _row(expect="oops")
    assert attention(_parked(), [row], [], step_word="x") == "your_turn"


def test_step_word_without_row_is_your_turn() -> None:
    assert attention(_parked(), [], [], step_word="x") == "your_turn"


def test_step_not_closed_reason_is_blocked() -> None:
    row = _row()
    run = _parked(park_reason=NOT_CLOSED)
    assert attention(run, [row], [_turn(row, 1, "done")], step_word=None) == "blocked"


def test_no_park_reason_is_your_turn() -> None:
    row = _row()
    run = _parked(park_reason=None)
    assert attention(run, [row], [_turn(row, 1, "done")], step_word=None) == "your_turn"


def test_round_two_with_only_first_turn_is_blocked() -> None:
    row = _row()
    run = _parked(inputs={"round_steps": "ux"})
    assert attention(run, [row], [_turn(row, 1, "done")], step_word=None) == "blocked"


def test_round_two_after_her_next_turn_is_your_turn() -> None:
    row = _row()
    run = _parked(inputs={"round_steps": "ux"})
    turns = [_turn(row, 1, "done"), _turn(row, 2, "done")]
    assert attention(run, [row], turns, step_word=None) == "your_turn"


def test_other_rows_and_roles_are_ignored() -> None:
    row, other = _row(), _row("prd")
    turns = [
        _turn(other, 1, "running"),
        _turn(row, 1, "running", role="agent"),
        _turn(row, 2, "error", role="consult"),
    ]
    assert attention(_parked(), [other, row], turns, step_word=None) == "your_turn"
