"""The `WorkflowEngine` adapter, behind one package (AD-2, AD-6).

`domain/` and `application/` take the `WorkflowEngine` port; `main.py` is the only module
that names an adapter from here. `LocalWorkflowEngine` is what it names until 4.6 lands the
durable, DBOS-backed one — see that class's own docstring for what it does and does not do.
"""

from __future__ import annotations

from orchestrator.infrastructure.engine.local import LocalWorkflowEngine

__all__ = ["LocalWorkflowEngine"]
