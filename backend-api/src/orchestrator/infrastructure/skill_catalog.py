"""Filesystem adapter for `SkillCatalog`: one skills manifest per harness under `agent_home`."""

from __future__ import annotations

import json
from pathlib import Path

#: Where `scripts/harness/_common.sh::write_skills_manifest` leaves each harness's catalog,
#: relative to `AGENT_HOME`. The harnesses resolve skills from different directories, so a
#: skill present for one is not present for another; `local` runs on opencode.
MANIFESTS: dict[str, Path] = {
    "claude": Path(".claude") / "skills-manifest.json",
    "codex": Path(".agents") / "skills-manifest.json",
    "opencode": Path(".config") / "opencode" / "skills-manifest.json",
    "local": Path(".config") / "opencode" / "skills-manifest.json",
}


def manifest_path(agent_home: Path, harness: str) -> Path | None:
    """The skills manifest of `harness` under `agent_home`, `None` for an unknown harness."""
    relative = MANIFESTS.get(harness)
    return agent_home / relative if relative is not None else None


class FsSkillCatalog:
    """Reads each harness's skills manifest from the local filesystem.

    Returns `None` (catalog unavailable) for an unknown harness and when the file is missing
    or unparseable; returns `frozenset[str]` of skill names on success.
    """

    def __init__(self, agent_home: Path) -> None:
        self._agent_home = agent_home

    def installed_skills(self, harness: str) -> frozenset[str] | None:
        """The skill names installed for `harness`, or `None` if its manifest is unavailable."""
        path = manifest_path(self._agent_home, harness)
        if path is None:
            return None
        try:
            data = json.loads(path.read_text())
            skills = data["skills"]
            if not isinstance(skills, list):
                return None
            return frozenset(skills)
        except OSError, KeyError, json.JSONDecodeError, TypeError:
            return None
