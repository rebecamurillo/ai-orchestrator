"""The durable engine adapter, behind one package (AD-6).

`dbos` is imported here and nowhere else in the system — `infrastructure/dbos/facade.py` is
the single module that names the library, and `pyproject.toml`'s forbidden contracts make
that checkable rather than a review note. Everything outside takes the `WorkflowEngine` port,
and `run.engine_ref` / `attempt.engine_ref` are opaque JSON only this package reads.

`main.py` names `build_engine`, `serving`, `launch_engine` and `schedule_jobs`; nothing
else here is public.
"""

from __future__ import annotations

from orchestrator.infrastructure.dbos.adapter import DbosWorkflowEngine
from orchestrator.infrastructure.dbos.config import EngineConfig, engine_config
from orchestrator.infrastructure.dbos.facade import RealEngine
from orchestrator.infrastructure.dbos.startup import (
    build_engine,
    launch_engine,
    schedule_jobs,
    serving,
)
from orchestrator.infrastructure.dbos.walker import WalkerDeps, build_walk

__all__ = [
    "DbosWorkflowEngine",
    "EngineConfig",
    "RealEngine",
    "WalkerDeps",
    "build_engine",
    "build_walk",
    "engine_config",
    "launch_engine",
    "schedule_jobs",
    "serving",
]
