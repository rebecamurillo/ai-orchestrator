"""The `Workspace` adapter, behind one package (AD-2, AD-14).

`domain/` and `application/` take the `Workspace` port; `pathlib`'s filesystem calls are
made only here.
"""

from __future__ import annotations

from orchestrator.infrastructure.workspace.fs import FsWorkspace

__all__ = ["FsWorkspace"]
