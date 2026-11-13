"""`role_of`: the one role an attempt is counted under (story 1, epic 2; RM-8)."""

from __future__ import annotations

import pytest

from orchestrator.application.metrics.roles import role_of
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ids import new_id
from tests.unit.fakes.chat_world import a_row


def attempt(role: str) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=new_id(),
        step_run_id=new_id(),
        n=1,
        status="done",
        role=role,  # type: ignore[arg-type]
    )


def test_a_consult_attempt_is_the_senior() -> None:
    assert role_of(attempt("consult"), a_row(new_id(), 1, "x", role="implement")) == "senior"


def test_a_session_attempt_is_chat() -> None:
    assert role_of(attempt("session"), a_row(new_id(), 1, "x", role="implement")) == "chat"


def test_an_agent_attempt_takes_the_rows_declared_role() -> None:
    assert role_of(attempt("agent"), a_row(new_id(), 1, "x", role="implement")) == "implement"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("epics[0].stories[1].build", "as declared: build"),
        ("steps[3]", "as declared: steps"),
        ("build", "as declared: build"),
    ],
)
def test_an_undeclared_role_reads_as_declared_from_the_path(path: str, expected: str) -> None:
    assert role_of(attempt("agent"), a_row(new_id(), 1, path, role="")) == expected
