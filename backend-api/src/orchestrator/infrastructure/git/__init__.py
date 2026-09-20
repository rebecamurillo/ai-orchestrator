"""Running git, behind one package (AD-2).

`domain/` and `application/` take the `Git` port; `subprocess`, `os` and `shutil` are
imported here and nowhere else, and `main.py` is the only module that names this adapter.
"""

from __future__ import annotations

from orchestrator.infrastructure.git.subprocess_git import SubprocessGit
from orchestrator.infrastructure.redact import redact

__all__ = ["SubprocessGit", "redact"]
