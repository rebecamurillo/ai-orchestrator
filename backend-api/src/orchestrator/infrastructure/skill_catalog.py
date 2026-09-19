"""Filesystem adapter for `SkillCatalog`: reads `{agent_home}/.claude/skills-manifest.json`."""

from __future__ import annotations

import json
from pathlib import Path


class FsSkillCatalog:
    """Reads the skills manifest from a path on the local filesystem.

    Returns `None` (catalog unavailable) when the file is missing or unparseable;
    returns `frozenset[str]` of skill names on success.
    """

    def __init__(self, manifest_path: Path) -> None:
        self._manifest_path = manifest_path

    def installed_skills(self) -> frozenset[str] | None:
        """The set of installed skill names, or `None` if the manifest is unavailable."""
        try:
            data = json.loads(self._manifest_path.read_text())
            skills = data["skills"]
            if not isinstance(skills, list):
                return None
            return frozenset(skills)
        except OSError, KeyError, json.JSONDecodeError, TypeError:
            return None
