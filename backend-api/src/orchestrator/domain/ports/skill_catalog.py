"""The `SkillCatalog` port: a read-only view of the installed-skills manifest of each harness.

`installed_skills` returns `None` when the manifest is unavailable (file not found,
unreadable, or unparseable) and a `frozenset[str]` of names otherwise.  `None` means
"catalog unavailable", and the pre-flight check answers it with a `fail` naming every skill
it could not verify — a manifest that cannot be read is a broken instance, not a quiet one
(hub-Run operations, skills install fix, 2026-09-24).  An empty frozenset means "no skills
installed", which is a different fact and fails per name.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SkillCatalog(Protocol):
    """A read-only view of the skills installed in the agent home."""

    def installed_skills(self, harness: str) -> frozenset[str] | None:
        """The skill names installed for `harness`, or `None` when its manifest is unavailable
        or the instance has no manifest for that harness."""
        ...
