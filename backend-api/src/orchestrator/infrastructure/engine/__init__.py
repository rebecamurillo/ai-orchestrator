"""The `WorkflowEngine` adapter, behind one package (AD-2, AD-6).

`domain/` and `application/` take the `WorkflowEngine` port. The adapter `main.py` names is
`infrastructure/dbos/`'s (4.6); `LocalWorkflowEngine` is the placeholder it named before that
and is now wired nowhere — see that class's own docstring for why it is still here.
"""

from __future__ import annotations

from orchestrator.infrastructure.engine.local import LocalWorkflowEngine

__all__ = ["LocalWorkflowEngine"]
