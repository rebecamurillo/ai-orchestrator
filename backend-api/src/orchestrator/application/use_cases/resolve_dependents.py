"""Dependency resolution between Runs (story 5-4, AD-8).

When a Run reaches a terminal status (`done`, `failed`, `cancelled`), any saved Run that
declared `after_run_id` pointing to it needs action:

- **Predecessor done** → the dependents should be enqueued (activate them). This function
  returns the list; the caller enqueues *after* committing, so the predecessor's durable
  status is visible to the engine before it tries to execute the dependent.
- **Predecessor failed or cancelled** → the dependents are parked with `park_kind=dependency`.
  Both writes (predecessor terminal + dependent park) happen in the **same** unit of work
  (AD-8: two writers, one UoW per transition).

**Why `set_run` directly instead of `park_run`:** `park_run` calls `run_transition(run.status,
"park")`, which requires the Run to be in `running` status (the only upstream of `needs_you`
in AD-8's diagram). A dependency-waiting Run is `queued`, not `running`, so `run_transition`
would raise `InvalidTransition`. Using `set_run` directly — the established precedent from
`_start_saved_run` and `_continue_dependency_park` — writes the status and park fields
atomically without passing through the machine pair that does not exist.
"""

from __future__ import annotations

from uuid import UUID

from orchestrator.application.use_cases.writers import Entry, WriterPorts, record, set_run
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.repositories import RunRepository

#: The `park_reason` written on a dependent whose predecessor did not finish `done`.
REASON_DEPENDENCY_ENDED = "run {x} ended {status}"


def _find_saved_dependents(runs: RunRepository, predecessor_id: UUID) -> list[Run]:
    """Every queued, not-yet-enqueued Run waiting for `predecessor_id`."""
    return [
        r
        for r in runs.list_by_status("queued")
        if r.after_run_id == predecessor_id and not r.engine_ref
    ]


def resolve_for_done(ports: WriterPorts, predecessor: Run) -> list[Run]:
    """Return the saved dependents of a *done* predecessor without writing anything.

    The caller commits the predecessor's status first, then calls `engine.enqueue` for each
    returned Run (outside the UoW), then writes `engine_ref` and clears `after_run_id` in a
    second UoW.  Keeping `after_run_id` set until `engine_ref` is written means the startup
    sweep can detect crash-residue (story 5-4 Design Notes).
    """
    return _find_saved_dependents(ports.runs, predecessor.id)


def resolve_for_failed_or_cancelled(ports: WriterPorts, predecessor: Run) -> None:
    """Park every saved dependent of a *failed or cancelled* predecessor as `dependency`.

    Must be called inside an already-open UoW so that the predecessor's terminal status and
    the dependent parks land in the same transaction.
    """
    reason = REASON_DEPENDENCY_ENDED.format(x=str(predecessor.id), status=predecessor.status)
    for dep in _find_saved_dependents(ports.runs, predecessor.id):
        # Use set_run directly: the dependent is `queued`, and RUN_TRANSITIONS has no
        # ("queued", "park") pair — the machine only parks from `running`.
        parked = set_run(
            ports,
            dep,
            status="needs_you",
            park_kind="dependency",
            park_path=None,
            park_reason=reason,
        )
        record(
            ports,
            parked,
            Entry(event="dependency", actor="machine", path=None, text=reason),
        )
