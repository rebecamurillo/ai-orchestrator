"""`writers_enqueue`: the two post-commit enqueues, moved out of `writers.py` (epic 8 story 1).
`writers` re-exports them, so no caller's import changes."""

from __future__ import annotations

from orchestrator.application.use_cases import writers, writers_enqueue
from tests.unit.application.writer_fixtures import PAIR_PLAN, a_world


def test_writers_re_exports_the_same_functions() -> None:
    assert writers.enqueue_dependents is writers_enqueue.enqueue_dependents
    assert writers.enqueue_saved_run is writers_enqueue.enqueue_saved_run


def test_without_an_engine_both_are_no_ops() -> None:
    world = a_world("queued", PAIR_PLAN)

    writers_enqueue.enqueue_saved_run(world.ports, None, world.run)
    writers_enqueue.enqueue_dependents(world.ports, None, world.run)

    assert world.engine.calls == []


def test_a_saved_run_is_enqueued_then_its_engine_ref_committed() -> None:
    world = a_world("queued", PAIR_PLAN)

    writers_enqueue.enqueue_saved_run(world.ports, world.engine, world.run)

    assert [name for name, _ in world.engine.calls] == ["enqueue"]
    assert world.stored_run().engine_ref == {"ref": 1}
    assert world.ports.uow.committed


def test_a_run_with_no_dependents_enqueues_nothing() -> None:
    world = a_world("done", PAIR_PLAN)

    writers_enqueue.enqueue_dependents(world.ports, world.engine, world.run)

    assert world.engine.calls == []
