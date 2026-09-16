"""The `Tracer` adapter, behind one package (AD-2, AD-11).

`domain/` and `application/` take the `Tracer` port; `langfuse` is imported only in
`langfuse_tracer.py`.  `NullTracer` imports no `langfuse` symbol at all.

`build_tracer(settings)` is the single decision point: when `settings.tracing_enabled`
is `True` it returns a `LangfuseTracer`; when `False` it returns a `NullTracer`.  No
other module in `application/` or `domain/` branches on this flag (AD-2).
"""

from __future__ import annotations

from orchestrator.domain.ports.tracer import Tracer

# `Settings` lives in the same layer (both are `infrastructure/`), so this import
# does not violate the AD-2 dependency direction.
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.tracing.langfuse_tracer import LangfuseTracer
from orchestrator.infrastructure.tracing.null import NullTracer


def build_tracer(settings: Settings) -> Tracer:
    """Return `LangfuseTracer(settings)` when tracing is enabled, else `NullTracer()`.

    This is the one place in the codebase that inspects `settings.tracing_enabled`
    for the tracer choice; call sites in `api/providers.py` and
    `infrastructure/dbos/startup.py` must use this factory rather than constructing
    `LangfuseTracer` directly.
    """
    if settings.tracing_enabled:
        return LangfuseTracer(settings)
    return NullTracer()


__all__ = ["LangfuseTracer", "NullTracer", "build_tracer"]
