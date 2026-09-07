"""The `ProcessRunner` adapter, behind one package (AD-2, AD-14).

`domain/` and `application/` take the `ProcessRunner` port; `subprocess`, `os` and `signal`
are imported only here.
"""

from __future__ import annotations

from orchestrator.infrastructure.process.runner import RealProcessRunner

__all__ = ["RealProcessRunner"]
