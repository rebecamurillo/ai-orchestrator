"""Filesystem adapter for `SkillCatalog`: reads `{agent_home}/.claude/skills-manifest.json`."""

from __future__ import annotations

import json
from pathlib import Path

#: Where `scripts/harness/_common.sh::write_skills_manifest` leaves the catalog, relative to
#: `AGENT_HOME`. Claude's copy is the one the orchestrator reads: all three harnesses receive
#: the same operator skills and the same BMAD stubs, under three different directories, so
#: any one of them answers "can this instance resolve this skill name".
MANIFEST_RELATIVE = Path(".claude") / "skills-manifest.json"


def manifest_path(agent_home: Path) -> Path:
    """The skills manifest for an instance whose harness home is `agent_home`.

    One statement of the path, because two readers need it — `api/providers.py` builds the
    catalog pre-flight reads, and `infrastructure/dbos/startup.py` builds the one the
    `agent` kind refuses an unresolvable skill with — and a drift between them would be
    invisible until a Run dispatched a skill nobody could resolve.
    """
    return agent_home / MANIFEST_RELATIVE


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
