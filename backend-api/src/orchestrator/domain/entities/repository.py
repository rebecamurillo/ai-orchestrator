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

`clone_check` starts `pending` and stays that way until `run_clone_check` writes a result;
nothing in this module executes a clone. A finished check carries one `CloneCheckLine` per
command it ran, and a `hint` — the third rule that lives here, because the API and the UI
both restate it. `hint` is derived rather than stored: it is a pure function of the status,
the summary output and the lines, so it needs no column of its own and cannot go stale
against the result it describes.
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

#: What `clone_check.status` can be. Only `run_clone_check` ever writes `"ok"` or
#: `"failed"`; a Repository that has never been checked reads, and stays, `"pending"`.
CloneCheckStatus = Literal["pending", "ok", "failed"]

#: What one checked command can be. A line is a command that ran, so it is never `pending`.
CloneCheckLineStatus = Literal["ok", "failed"]

#: The four commands a check reports, in the order it runs them. Named here so the use case,
#: the API and the UI cannot each spell them differently.
LINE_LS_REMOTE = "ls-remote"
LINE_CLONE = "clone"
LINE_DEFAULT_BRANCH = "default branch"
LINE_METHOD_VERSION = "method version"

#: What `bmad_version` says when the repository carries no readable `installation.version`,
#: and when it carries one that is not the version this instance runs (FR-30).
MISSING_VERSION = "missing"
OUTDATED_VERSION = "outdated"

#: The failures that have an answer, and the answer. `output` is git's sentence; these are
#: what the Operator can act on.
AUTH_HINT = "the instance's GitHub token has no access to this repository"
NOT_FOUND_HINT = "repository not found: check the URL"

#: What git says when the credential was refused, and when nothing answered to the URL.
#: The auth patterns are checked first: they mean the credential failed and nothing else,
#: while `Repository not found` is also what a private repository answers a valid token.
#: Two not-found patterns because two transports word it differently — an https remote says
#: `Repository not found`, a local or `file://` one says the path is not a repository — and
#: the Operator's next step is the same either way: look at the URL.
AUTH_PATTERNS = ("Authentication failed", "could not read Username")
NOT_FOUND_PATTERNS = (
    "Repository not found",
    "does not appear to be a git repository",
)

#: What the default-branch line says when the origin does not hold the branch. The line's
#: own words are the hint, so the branch name reaches the Operator without being stored
#: twice; a branch line that failed for any other reason is not a missing branch.
MISSING_BRANCH_PATTERN = "does not exist on origin"

#: Every Repository protects at least these, whatever the Operator asked for.
DEFAULT_TEST_GLOBS: tuple[str, ...] = ("tests/**", "**/*.test.*", "**/*.spec.*")

#: The suffix a git URL's last path segment carries, and never keeps as part of the slug.
GIT_SUFFIX = ".git"


class CloneCheckLine(BaseModel):
    """One command the check ran, how long it took, and what it said."""

    model_config = ConfigDict(frozen=True)

    name: str
    status: CloneCheckLineStatus
    seconds: float
    output: str


class CloneCheck(BaseModel):
    """The result of the last attempt to reach and clone this Repository."""

    model_config = ConfigDict(frozen=True)

    status: CloneCheckStatus
    at: datetime | None
    output: str
    bmad_version: str | None
    #: One entry per command that ran, in the order they ran. Defaulted, so a check written
    #: before lines existed — and every row already stored — reads back unchanged.
    lines: tuple[CloneCheckLine, ...] = ()

    @classmethod
    def pending(cls) -> CloneCheck:
        """The value every new Repository starts with: no attempt has run yet."""
        return cls(status="pending", at=None, output="", bmad_version=None)

    @property
    def hint(self) -> str:
        """What the Operator can do about this failure, or `""` when nothing is known.

        Derived from what the check already holds, so it cannot disagree with it. Order
        matters: a refused credential says so unambiguously, while `Repository not found` is
        what a private repository answers a token that cannot see it as well as what any
        remote answers a name that is not there.
        """
        if self.status != "failed":
            return ""
        failed = [line for line in self.lines if line.status == "failed"]
        said = "\n".join([self.output, *(line.output for line in failed)])
        if any(pattern in said for pattern in AUTH_PATTERNS):
            return AUTH_HINT
        if any(pattern in said for pattern in NOT_FOUND_PATTERNS):
            return NOT_FOUND_HINT
        for line in failed:
            if line.name == LINE_DEFAULT_BRANCH and MISSING_BRANCH_PATTERN in line.output:
                return line.output
        return ""


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
