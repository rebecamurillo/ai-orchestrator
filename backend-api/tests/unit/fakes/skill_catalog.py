"""In-memory `SkillCatalog` — the one fake for that port (AD-18). Do not write another.

The catalog is a mapping harness → names. A harness absent from the mapping, or mapped to
`None`, is a catalog that is unavailable for it; an empty `frozenset()` is a catalog with no
skills installed. `asked` records every harness the code under test asked about.
"""

from __future__ import annotations

from collections.abc import Mapping

from orchestrator.domain.ports.skill_catalog import SkillCatalog


class FakeSkillCatalog:
    """Returns the fixed set of skill names of each harness, `None` for an unavailable one."""

    def __init__(self, skills: Mapping[str, frozenset[str] | None] | None = None) -> None:
        self._skills = dict(skills or {})
        self.asked: list[str] = []

    def installed_skills(self, harness: str) -> frozenset[str] | None:
        self.asked.append(harness)
        return self._skills.get(harness)


assert isinstance(FakeSkillCatalog(), SkillCatalog)
