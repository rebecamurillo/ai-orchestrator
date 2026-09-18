"""What pre-flight speaks in: one request, twelve check lines, and the outcome (FR-8).

`PreflightRequest` mirrors `POST /runs/preflight`'s body field for field; every field but
`re_review_done` is optional, because the brief's own rule is that a missing field makes
its dependent lines `skip` rather than a 422 — the New-workflow screen calls pre-flight on
every keystroke, long before the form is complete.

`Line.check` is the fixed category name from the brief's numbered list (`"origin
reachable"`, `"branch"`, …); `Line.text` carries every substitution. Neither is asserted
verbatim by the brief's acceptance criteria beyond what `Line.text` states for lines 1, 3, 8
and 9 — the split is this module's own, kept stable so a caller can group lines by category.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from orchestrator.application.templates.plan_model import PlanError
from orchestrator.domain.values import PlannedRow

LineStatus = Literal["ok", "warn", "fail", "skip"]

# --- the fixed check names, in FR-8 order ---------------------------------------------------

CHECK_ORIGIN = "origin reachable"
CHECK_BASE_BRANCH = "base branch"
CHECK_BRANCH = "branch"
CHECK_EPICS_YAML = "epics.yaml"
CHECK_STORIES_YAML = "stories.yaml"
CHECK_CHECKPOINTS = "checkpoints"
CHECK_SPEC_MD = "SPEC.md"
CHECK_HARNESS = "harness"
CHECK_INSTALLED_SKILL = "installed skill"
CHECK_METHOD_VERSION = "method version"
CHECK_EXISTING_STORY_FILES = "existing story files"
CHECK_CLONE_CHECK = "clone check"
CHECK_WHAT_WILL_RUN = "what will run"
CHECK_CONCURRENT_REPO = "concurrent branch"

#: The default `queue_note` — nothing holds the Repository and the instance is under its cap.
QUEUE_FREE = "starts immediately if the repository is free"


@dataclass(frozen=True)
class Line:
    """One rendered check line. `fix` is set only when `status` is `"fail"`."""

    check: str
    status: LineStatus
    text: str
    fix: str | None = None


@dataclass(frozen=True)
class PreflightRequest:
    """`POST /runs/preflight`'s body, field for field. Every field but `re_review_done` is
    optional (see the module docstring)."""

    template_name: str | None = None
    template_version: int | None = None
    project_id: UUID | None = None
    repository_id: UUID | None = None
    base_branch: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    harness: str | None = None
    model: str | None = None
    budget_usd: Decimal | None = None
    re_review_done: bool = False


@dataclass(frozen=True)
class PreflightResult:
    """What `run_preflight` returns: every line, whether a Run may start, and what it would
    plan."""

    lines: tuple[Line, ...]
    start_allowed: bool
    queue_note: str
    rows: tuple[PlannedRow, ...] | None
    plan_error: PlanError | None
    conflict_consent_required: bool = False
