"""A Template Version: the immutable YAML a Run is planned from, and what it calls.

Two rules live here because three layers restate them, and a copy of either would be the
copy that drifts:

- **A version is identified by `(name, version)`.** Saving a Template creates version n+1;
  a version pinned by any Run, directly or as a callee, is frozen (AD-15). Nothing here
  mutates: the model is frozen, and a new version is a new object.
- **`calls` is the pinned callee list, recorded when the version was saved.** The validator
  walks it to find cycles and to measure call depth without re-reading — and without
  re-validating — a callee's body, which was validated when it was saved.

`hash` is the digest of `yaml`; computing it needs no rule, so it is carried rather than
derived here. `yaml` is the exact text the Operator saved, newlines and comments included:
line numbers in a `ValidationError` refer to it.

`id` and `created_at` default to `None` because 3.1's fixtures build a `TemplateVersion`
without either — they describe rows a fake never persists. 3.3's use cases (`save_version`,
`seed_shipped`) always fill both before a version reaches a repository: `id` is a fresh
UUIDv7 (`domain/ids.py`), `created_at` the instant `Clock.now()` returned. Only
`infrastructure/` reads a clock (`test_source_limits.py`), so neither is computed here.

`TemplateSummary` is the read model `GET /templates` renders: one row per stored name, the
version numbers it holds, and the description of its latest version — denormalised onto the
`template` table at save time so a list read never re-parses every version's YAML.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TemplateRef(BaseModel):
    """One `(name, version)` pair: a Template Version named, not loaded."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: int


class TemplateVersion(BaseModel):
    """A stored Template Version: its text, its digest, and the callees it pins."""

    model_config = ConfigDict(frozen=True)

    #: The `template_version` row's primary key. `None` only in a fixture that never
    #: stores this object — a real save always sets it before calling `add_version`.
    id: UUID | None = None
    name: str
    version: int
    yaml: str
    hash: str
    calls: tuple[TemplateRef, ...] = ()
    #: `None` only in a fixture; a real save always sets it (see the module docstring).
    created_at: datetime | None = None

    def ref(self) -> TemplateRef:
        """This version as a reference — what a caller's `calls` entry holds."""
        return TemplateRef(name=self.name, version=self.version)


class TemplateSummary(BaseModel):
    """One row of `GET /templates`: a name, its description, and the versions it holds."""

    model_config = ConfigDict(frozen=True)

    name: str
    #: The latest version's parsed `description:`, or `None` if it declared none.
    description: str | None = None
    latest_version: int
    #: Every stored version number of this name, ascending.
    versions: tuple[int, ...] = ()
