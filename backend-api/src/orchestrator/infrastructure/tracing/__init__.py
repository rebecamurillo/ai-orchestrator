"""The `Tracer` adapter, behind one package (AD-2, AD-11).

`domain/` and `application/` take the `Tracer` port; `langfuse` is imported only here.
"""

from __future__ import annotations

from orchestrator.infrastructure.tracing.langfuse_tracer import LangfuseTracer

__all__ = ["LangfuseTracer"]
