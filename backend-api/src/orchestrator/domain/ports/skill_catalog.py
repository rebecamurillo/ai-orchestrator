"""The `SkillCatalog` port: a read-only view of the installed-skills manifest.

`installed_skills` returns `None` when the manifest is unavailable (file not found,
unreadable, or unparseable) and a `frozenset[str]` of names otherwise.  `None` means
"catalog unavailable" and is treated as `skip` by the pre-flight check; an empty
frozenset means "no skills installed".
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SkillCatalog(Protocol):
    """A read-only view of the skills installed in the agent home."""

    def installed_skills(self) -> frozenset[str] | None:
        """The set of installed skill names, or `None` if the manifest is unavailable."""
        ...
