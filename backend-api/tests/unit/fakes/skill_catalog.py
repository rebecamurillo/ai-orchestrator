"""In-memory `SkillCatalog` — the one fake for that port (AD-18). Do not write another.

`None` simulates a catalog that is unavailable (manifest file missing or unreadable).
An empty `frozenset()` simulates a catalog with no skills installed.
"""

from __future__ import annotations

from orchestrator.domain.ports.skill_catalog import SkillCatalog


class FakeSkillCatalog:
    """Returns a fixed set of skill names, or `None` to simulate an unavailable catalog."""

    def __init__(self, skills: frozenset[str] | None = frozenset()) -> None:
        self._skills = skills

    def installed_skills(self) -> frozenset[str] | None:
        return self._skills


assert isinstance(FakeSkillCatalog(), SkillCatalog)
