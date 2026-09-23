"""Startup sweep for dependency-waiting Runs whose predecessor terminated before boot.

When the process crashes between a predecessor reaching a terminal status (`done`,
`failed`, or `cancelled`) and the dependent being enqueued or parked, the dependent is left
`queued` with `engine_ref={}` and its `after_run_ids` still listing that predecessor. This
sweep re-applies the resolution on startup, which is what makes crash recovery idempotent
(AD-12: "container start sweeps the residue of any crash").

It decides nothing of its own. The rule is `writers.resolve_dependent` — the same function
the two run-time writers (`apply_step_result`, `signal_run`) reach through
`park_dependents` / `enqueue_dependents` — so a Run resolved at boot and a Run resolved
mid-flight can never take different paths.

This is a pure application function: it reads through `WriterPorts` and touches no adapter.
"""

from __future__ import annotations

from orchestrator.application.use_cases.writers import WriterPorts, resolve_dependent
from orchestrator.domain.ports.engine import WorkflowEngine


def sweep_dependency_waiting(ports: WriterPorts, engine: WorkflowEngine | None) -> None:
    """Re-resolve every dependency-waiting Run a crash left un-enqueued and un-parked.

    The set is AD-12's own: `queued`, a non-empty `after_run_ids`, and an empty
    `engine_ref`. Each one is resolved on its own — all predecessors `done` → two-phase
    enqueue; any of them `failed | cancelled` or gone → `dependency` park naming it;
    otherwise nothing.

    Idempotent in both directions, because the write each path makes is what removes the
    Run from the set: an enqueued Run has an `engine_ref`, a parked Run is `needs_you`. A
    second sweep therefore enqueues nothing more and writes no second gate record.
    """
    for run in ports.runs.list_by_status("queued"):
        if run.after_run_ids and not run.engine_ref:
            resolve_dependent(ports, engine, run)
