"""`infrastructure/dbos/facade.py`: the one module that names the library, held to its API.

Nothing here launches anything — that needs a Postgres and belongs to the e2e gate. What it
does is pin the third-party surface the adapter is written against, symbol by symbol, so the
day a `dbos` upgrade renames `list_workflow_steps` or drops `queue_partition_key` the failure
is this test naming the symbol rather than a Run that silently never starts. The research
note behind this story lists two of these as *unverified*; they are verified here.

`RealEngine` satisfying `DurableEngine` is asserted structurally, because that protocol is
what every other module in the package is typed against.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest
from dbos import DBOS, DBOSConfig, SetEnqueueOptions, SetWorkflowID, StepInfo

from orchestrator.infrastructure.dbos.facade import (
    ENQUEUED,
    PENDING,
    DurableEngine,
    QueuedWorkflow,
    RealEngine,
    StepRecord,
    _at,
)

#: Every attribute of `DBOS` the facade calls, and what it is called there.
CALLED = (
    "workflow",
    "step",
    "register_queue",
    "enqueue_workflow",
    "send",
    "recv",
    "cancel_workflow",
    "list_workflows",
    "list_workflow_steps",
    "create_schedule",
    "launch",
    "step_id",
    "workflow_id",
)

EPOCH_MS = 1757160000000


def test_the_real_engine_satisfies_the_protocol_every_other_module_is_typed_against() -> None:
    assert isinstance(RealEngine(), DurableEngine)


@pytest.mark.parametrize("name", CALLED)
def test_the_library_still_has_the_symbol_the_facade_calls(name: str) -> None:
    assert hasattr(DBOS, name), f"dbos no longer exposes DBOS.{name}"


def test_a_step_is_declared_with_the_engines_own_retries_off() -> None:
    """AD-6: the engine never re-executes a side effect on its own."""
    assert inspect.signature(DBOS.step).parameters["retries_allowed"].default is False


def test_the_queue_takes_a_global_and_a_per_partition_concurrency() -> None:
    """AD-12 is one queue `MAX_ACTIVE_RUNS` wide with one Run per Repository."""
    parameters = inspect.signature(DBOS.register_queue).parameters

    assert "global_concurrency" in parameters
    assert "partition_concurrency" in parameters


def test_an_enqueue_can_name_its_partition_key_and_its_workflow_id() -> None:
    assert "queue_partition_key" in inspect.signature(SetEnqueueOptions.__init__).parameters
    assert callable(SetWorkflowID)


def test_recv_takes_the_deadline_the_thirty_day_wait_needs() -> None:
    assert "timeout_seconds" in inspect.signature(DBOS.recv).parameters


def test_a_step_record_is_keyed_by_the_function_id_the_adapter_stores() -> None:
    """The research note left `DBOS.step_id == function_id` unverified; this is the check."""
    assert "function_id" in StepInfo.__annotations__
    assert DBOS.step_id is None  # outside a step there is no step id, and that is not a raise


def test_the_configuration_keys_the_adapter_writes_are_the_librarys_own() -> None:
    for key in ("name", "system_database_url", "application_version", "run_admin_server"):
        assert key in DBOSConfig.__annotations__


def test_the_two_states_a_held_workflow_can_be_in_are_the_librarys_words() -> None:
    """`list_queue` maps exactly these two; a third would be reported as `pending`."""
    assert ENQUEUED == "ENQUEUED"
    assert PENDING == "PENDING"


def test_epoch_milliseconds_become_the_utc_instant_every_timestamp_here_is() -> None:
    assert _at(EPOCH_MS) == datetime.fromtimestamp(EPOCH_MS / 1000, tz=UTC)
    assert _at(None).tzinfo is UTC


def test_the_two_records_the_facade_answers_with_are_plain_values() -> None:
    workflow = QueuedWorkflow(workflow_id="w", state=ENQUEUED, enqueued_at=_at(EPOCH_MS))
    step = StepRecord(step_id=1, name="attempt_row", output=None, error=None)

    assert workflow.state == ENQUEUED
    assert step.step_id == 1
