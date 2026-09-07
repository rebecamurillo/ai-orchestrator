"""What the durable engine is configured with, as values (AD-6, AD-12, AD-20).

Reading `Settings` here and nowhere else in this package keeps the adapter and the walker
free of the environment: they take an `EngineConfig` and can be built in a test from four
numbers. `dbos_config` is the shape the library's own constructor takes, built as a plain
mapping so this module says what the engine is configured with without the rest of the
package having to agree on a third-party type.

Three of the values carry a rule:

- **`application_version`** is `DBOS_APPLICATION_VERSION`, not a hash of the walker's
  source. The library's default changes whenever the source does, and a changed version
  makes running workflows unrecoverable; pinning it means the walker's step sequence is
  changed deliberately, by bumping the setting after draining active Runs (AD-6). It is a
  string here because the library's field is one; the setting stays an integer.
- **The system database is the application's** (`DATABASE_URL`), in schema `dbos` — which
  is the library's own default, so nothing sets it. Alembic manages `public` only, and
  `tests/e2e/test_migrations.py` holds it to that.
- **`run_admin_server` is off.** It binds a second port that answers no product route.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orchestrator.infrastructure.settings import Settings

#: The one queue every Run is enqueued on (AD-12). Partitioned by `repository_id`.
QUEUE_NAME = "runs"

#: The topic a Run's single human wait listens on (AD-13).
HUMAN_TOPIC = "human:{run_id}"

#: What the engine calls this application in its own tables; two applications sharing one
#: database are told apart by it.
APP_NAME = "ai-orchestrator"

#: The keys of an `engine_ref` (AD-6). Opaque outside this package: `run.engine_ref` is the
#: workflow, `attempt.engine_ref` is the workflow and the step inside it that ran the row.
WORKFLOW_ID = "workflow_id"
STEP_ID = "step_id"


@dataclass(frozen=True)
class EngineConfig:
    """Everything the engine adapter needs from the environment, and nothing else."""

    database_url: str
    application_version: str
    max_active_runs: int


def engine_config(settings: Settings) -> EngineConfig:
    """The typed environment, narrowed to the engine's three values (AD-20).

    `HUMAN_WAIT_SECONDS` is deliberately not here: the deadline is the walker's, and it
    reaches it through `startup.walker_deps`. Carrying it on both would read as the wiring
    while only one of them was it.
    """
    return EngineConfig(
        database_url=settings.database_url.get_secret_value(),
        application_version=str(settings.dbos_application_version),
        max_active_runs=settings.max_active_runs,
    )


def dbos_config(config: EngineConfig) -> dict[str, Any]:
    """The library's own configuration mapping, built from `EngineConfig`."""
    return {
        "name": APP_NAME,
        "system_database_url": config.database_url,
        "application_version": config.application_version,
        "run_admin_server": False,
    }
