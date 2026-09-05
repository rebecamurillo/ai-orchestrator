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
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TemplateRef(BaseModel):
    """One `(name, version)` pair: a Template Version named, not loaded."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: int


class TemplateVersion(BaseModel):
    """A stored Template Version: its text, its digest, and the callees it pins."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: int
    yaml: str
    hash: str
    calls: tuple[TemplateRef, ...] = ()

    def ref(self) -> TemplateRef:
        """This version as a reference — what a caller's `calls` entry holds."""
        return TemplateRef(name=self.name, version=self.version)
