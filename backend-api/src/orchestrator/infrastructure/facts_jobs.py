"""The facts sweep, wired to the adapters (AGENTS.md "Data capture").

Registered through its own `schedule_facts_jobs`, not through `jobs.scheduled_jobs`.
"""

from __future__ import annotations

from collections.abc import Callable

from orchestrator.application.jobs.facts_sweep import run_facts_sweep
from orchestrator.infrastructure.db.writers import SessionFactory, open_facts_ports
from orchestrator.infrastructure.harness.facts import build_log_facts
from orchestrator.infrastructure.settings import Settings

FACTS_SWEEP_NAME = "facts_sweep"


def facts_jobs(
    settings: Settings, session_factory: SessionFactory
) -> list[tuple[str, str, Callable[[], None]]]:
    """`(name, cron, job)`; building the job opens no session."""

    def job() -> None:
        with open_facts_ports(
            session_factory, build_log_facts(settings), subscription_auth=None
        ) as ports:
            run_facts_sweep(ports)

    return [(FACTS_SWEEP_NAME, settings.facts_sweep_cron, job)]
