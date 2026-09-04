"""The Repository: where a Run's clone lives, and the commands it runs there.

Two rules live here because two layers restate them, and a copy would be the copy that
drifts:

- **A slug is derived once**, from the URL's last path segment with a trailing `.git`
  stripped, run through the same character rule as `Project.slugify` (lowercase,
  `[a-z0-9-]`). It identifies the Repository to an Operator reading a list; a `PUT` that
  changed the URL must not silently rename what they already recognise, so nothing here
  ever recomputes it after creation.
- **`test_globs` always protects the three defaults.** An agent step in Epic 4 refuses to
  touch a path one of these globs names; an Operator narrowing the set by omission — rather
  than only ever broadening it — would be a protection that silently disappeared.
  `merge_test_globs` is why a `POST`/`PUT` payload can only add to the set, never replace
  it.

`clone_check` starts `pending` and stays that way until 2.3's `run_clone_check` writes a
result; nothing in this module executes a clone.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from orchestrator.domain.entities.project import slugify

#: What a Repository's package manager can be. `"other"` is what a create that never states
#: one gets, matching the minimal-create row of the story's I/O matrix.
PackageManager = Literal["uv", "pnpm", "npm", "yarn", "pip", "cargo", "go", "other"]
DEFAULT_PACKAGE_MANAGER: PackageManager = "other"

#: What `clone_check.status` can be. Only `run_clone_check` (2.3) ever writes `"ok"` or
#: `"failed"`; every Repository this story creates starts, and stays, `"pending"`.
CloneCheckStatus = Literal["pending", "ok", "failed"]

#: Every Repository protects at least these, whatever the Operator asked for.
DEFAULT_TEST_GLOBS: tuple[str, ...] = ("tests/**", "**/*.test.*", "**/*.spec.*")

#: The suffix a git URL's last path segment carries, and never keeps as part of the slug.
GIT_SUFFIX = ".git"


class CloneCheck(BaseModel):
    """The result of the last attempt to clone and install this Repository (2.3)."""

    model_config = ConfigDict(frozen=True)

    status: CloneCheckStatus
    at: datetime | None
    output: str
    bmad_version: str | None

    @classmethod
    def pending(cls) -> CloneCheck:
        """The value every new Repository starts with: no attempt has run yet."""
        return cls(status="pending", at=None, output="", bmad_version=None)


class Repository(BaseModel):
    """A git repository a Run works in, as it is stored."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    project_id: UUID
    slug: str
    url: str
    default_branch: str
    install_command: str
    quality_gate_command: str
    unit_test_command: str
    test_globs: tuple[str, ...]
    package_manager: PackageManager
    clone_check: CloneCheck
    created_at: datetime
    updated_at: datetime

    @property
    def verify_skipped(self) -> bool:
        """No quality-gate command means nothing verifies a Run's work in this Repository.

        A whitespace-only command is not a declared one: `.strip()` is what keeps `" "`
        from reading as `verify_skipped is False`.
        """
        return not self.quality_gate_command.strip()


def repo_slug(url: str) -> str:
    """The URL's last path segment, `.git` stripped, through the same rule as a Project's."""
    last_segment = url.rstrip("/").rsplit("/", 1)[-1]
    if last_segment.endswith(GIT_SUFFIX):
        last_segment = last_segment[: -len(GIT_SUFFIX)]
    return slugify(last_segment)


def merge_test_globs(requested: Iterable[str]) -> tuple[str, ...]:
    """The defaults, then whatever the Operator asked for that is not already among them.

    Order-preserving and de-duplicated: a requested glob already in the defaults is not
    repeated, and two equal requested globs collapse to the one that appeared first.
    """
    merged = list(DEFAULT_TEST_GLOBS)
    for glob in requested:
        if glob not in merged:
            merged.append(glob)
    return tuple(merged)
