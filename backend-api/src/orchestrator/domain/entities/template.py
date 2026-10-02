"""A Template Version: the immutable YAML a Run is planned from, and what it calls.

Two rules live here because three layers restate them, and a copy of either would be the
copy that drifts:

- **A version is identified by `(name, version)`.** Saving a Template creates version n+1;
  a version pinned by any Run, directly or as a callee, is frozen (AD-15). Nothing here
  mutates: the model is frozen, and a new version is a new object.
- **`calls` is the callee list as the file wrote it, recorded when the version was saved.**
  A call that named an integer `version` is a pin (`TemplateRef`); one that omitted it is
  unpinned (`TemplateCallRef` with `version=None`) and resolves to the callee's latest
  stored version whenever the caller is validated or planned — so a Run planned later
  follows a newer callee, and a Run already planned never does (its own pins are the
  resolved integers). The validator walks `calls` to find cycles and to measure call depth
  without re-reading — and without re-validating — a callee's body.

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


class TemplateCallRef(BaseModel):
    """A callee as a `uses: template` step named it: by name, pinned to a version or not.

    Equality is by `(name, version)` whichever subclass carries them, because a stored
    `calls` entry and a Run's pin name the same callee when those two agree.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    version: int | None

    @property
    def pinned(self) -> bool:
        return self.version is not None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TemplateCallRef):
            return NotImplemented
        return (self.name, self.version) == (other.name, other.version)

    def __hash__(self) -> int:
        return hash((self.name, self.version))


class TemplateRef(TemplateCallRef):
    """One `(name, version)` pair: a Template Version named, not loaded."""

    version: int


def call_ref(name: str, version: int | None) -> TemplateCallRef:
    """A `TemplateRef` when the version is known, else an unpinned `TemplateCallRef`."""
    if version is None:
        return TemplateCallRef(name=name, version=None)
    return TemplateRef(name=name, version=version)


class TemplateCaller(BaseModel):
    """One `called_by` entry: the caller's version, and whether its call pinned this one."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: int
    pinned: bool


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
    calls: tuple[TemplateCallRef, ...] = ()
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
