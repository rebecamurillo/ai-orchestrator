"""`RealEngine.enqueue` from inside a step runs in a fresh `contextvars.Context`: the library
refuses to start a workflow from a step, and a Run's terminal write — which queues its metrics
calculation (epic 2 story 5) — runs inside the walker's `apply_result` step. Outside a step the
enqueue keeps the caller's context, so a workflow's own enqueue stays its child."""

from __future__ import annotations

from typing import Any

import pytest
from dbos._context import DBOSContext, _dbos_context_var, get_local_dbos_context

from orchestrator.infrastructure.dbos import facade
from orchestrator.infrastructure.dbos.facade import RealEngine

STEP_FUNCTION_ID = 3


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def enqueue_workflow(queue: str, workflow: object, run_id: str) -> None:
        ctx = get_local_dbos_context()
        calls.append(
            {
                "queue": queue,
                "run_id": run_id,
                "in_step": ctx is not None and ctx.is_step(),
                "parent": ctx.workflow_id if ctx is not None else "",
                "assigned": ctx.id_assigned_for_next_workflow if ctx is not None else "",
            }
        )

    monkeypatch.setattr(facade.DBOS, "enqueue_workflow", enqueue_workflow)
    return calls


def a_context(*, step: bool) -> DBOSContext:
    ctx = DBOSContext()
    ctx.workflow_id = "walk-of-run-a"
    if step:
        ctx.curr_step_function_id = STEP_FUNCTION_ID
    return ctx


def test_an_enqueue_inside_a_step_starts_outside_the_workflow(seen: list[dict[str, Any]]) -> None:
    token = _dbos_context_var.set(a_context(step=True))
    try:
        RealEngine().enqueue("session", lambda: None, "calc-1", partition_key="calc-1")
        ctx = get_local_dbos_context()
        assert ctx is not None and ctx.is_step()
    finally:
        _dbos_context_var.reset(token)

    assert seen == [
        {
            "queue": "session",
            "run_id": "calc-1",
            "in_step": False,
            "parent": "",
            "assigned": "calc-1",
        }
    ]


def test_an_enqueue_from_the_workflow_body_keeps_its_context(seen: list[dict[str, Any]]) -> None:
    token = _dbos_context_var.set(a_context(step=False))
    try:
        RealEngine().enqueue("session", lambda: None, "turn-1", partition_key="run-a")
    finally:
        _dbos_context_var.reset(token)

    (call,) = seen
    assert (call["in_step"], call["parent"], call["assigned"]) == (
        False,
        "walk-of-run-a",
        "turn-1",
    )


def test_an_enqueue_with_no_context_at_all_is_unchanged(seen: list[dict[str, Any]]) -> None:
    RealEngine().enqueue("runs", lambda: None, "run-b", partition_key="repo-1")

    (call,) = seen
    assert (call["in_step"], call["parent"], call["assigned"]) == (False, "", "run-b")
