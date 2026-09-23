"""The Run: one execution of one pinned Template Version against one Repository (AD-7).

The entity is frozen and has no method that changes a field. That is the whole point: AD-8
gives status exactly two writers — `apply_step_result` for execution transitions and
`signal_run` for operator ones — and a mutable Run would let a router, an executor or an
adapter become a third. A change is a `model_copy(update=...)` handed to
`RunRepository.update`, so every write passes through a repository call some test can see.

Three fields carry a rule the columns alone do not state:

- **`pinned_versions` is the whole call tree, pinned at plan time** (AD-15). It reuses
  `TemplateRef` rather than a second `(name, version)` pair type, because a Run's pins and a
  Template's `calls` are the same thing named from two sides.
- **`manual_estimate_h` is immutable after the Run starts.** Nothing here enforces it —
  4.4's `create_run` and 4.5's writers do — but it is the reason the field is `None` rather
  than `0`: an estimate nobody gave is absent, not zero.
- **`park_kind`, `park_path` and `park_reason` are written together** with the `gate_record`
  when a `StepResult.park` arrives, and cleared together by `signal_run`. A Run in
  `needs_you` always has all three; a Run in any other status has none of them.

Fields a later story fills are defaulted rather than required, so 4.4 can create a Run from
what the Operator submitted without inventing values for the planner (`plan_ref`), the
engine adapter (`engine_ref`), the tracer (`trace_id`) or the git steps (`worktrees`).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.domain.entities.template import TemplateRef
from orchestrator.domain.statuses import ParkKind, RunStatus
from orchestrator.domain.values import Worktree


class Run(BaseModel):
    """One Run, as it is stored."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    project_id: UUID
    repository_id: UUID
    #: The Template Version this Run was planned from — the root of `pinned_versions`.
    template_name: str
    template_version: int
    #: Every version the plan pinned, root and callees, in the order the planner walked
    #: them (AD-15).
    pinned_versions: tuple[TemplateRef, ...] = ()
    #: The bound inputs: `base_branch`, `harness`, `model` and whatever the Template
    #: declared. Read whole, never queried into.
    inputs: dict[str, Any] = Field(default_factory=dict)
    status: RunStatus
    #: The commit the plan was read at. `None` until `plan_run` has run.
    plan_ref: str | None = None
    #: `{path: sha}` — the commit each list file was read at, so a plan can be called stale.
    plan_refs: dict[str, str] = Field(default_factory=dict)
    #: Opaque JSON the durable-engine adapter owns; nothing outside `infrastructure/dbos/`
    #: reads a key of it (AD-6).
    engine_ref: dict[str, Any] = Field(default_factory=dict)
    budget_usd: Decimal | None
    spend_usd: Decimal = Decimal("0")
    spend_provisional: bool = False
    #: Hours the Operator estimated the same work would take by hand. Immutable after start.
    manual_estimate_h: Decimal | None = None
    re_review_done: bool = False
    park_kind: ParkKind | None = None
    park_path: str | None = None
    park_reason: str | None = None
    #: Files a `continue` on `protected_path` accepted; every later check in the same story
    #: frame excludes them (AD-9).
    accepted_paths: tuple[str, ...] = ()
    #: The worktree the Run is working in now.
    worktree_path: str | None = None
    #: Every worktree the Run has created, current one included.
    worktrees: tuple[Worktree, ...] = ()
    compare_urls: tuple[str, ...] = ()
    #: Whether `worktree_gc` (SPEC CAP-11, FR-9) has already swept this Run's worktrees and
    #: logs — what makes the job's own sweep idempotent (AD-14). `worktrees` itself is left
    #: as history rather than cleared, so a Run's own record still says which branch it
    #: worked on after the files are gone. A `bool` rather than a `removed_at` timestamp
    #: (the brief's own suggestion): `tests/unit/test_run_repository_adapter.py`'s closed
    #: set of nullable `run` columns is frozen (hard rule 1), and a `NOT NULL` column with a
    #: default reaches the same idempotency without joining that set — see this story's
    #: Design Notes.
    worktrees_removed: bool = False
    #: The declared branch this Run partitions its queue slot by (AD-12, story 5-1). Set once
    #: at `create_run` time from `plan.branches`; never written again. `None` on old runs that
    #: pre-date this field — those runs are treated as non-competing for branch-partition checks.
    partition_branch: str | None = None
    #: The Runs this one waits for before it may enter the engine (AD-12) — a fan-in list,
    #: empty by default, in the order the caller declared them. All of them `done` enqueues
    #: this Run; any of them `failed | cancelled` parks it `dependency`, naming that one.
    #: Nothing ever clears the list: resolution only considers Runs whose `engine_ref` is
    #: null, so clearing buys nothing, and the retained edges are the durable record an
    #: initiative's DAG is rendered from (spine AD-12/AD-13 amendment, 2026-09-23).
    after_run_ids: tuple[UUID, ...] = ()
    #: The Langfuse trace this Run's attempt spans hang under (AD-11).
    trace_id: str | None = None
    terminal_session: bool = False
    #: How many consecutive `terminal_poll` fires have found the Story file `done` and the
    #: tree clean (AD-13, AD-14, FR-21). Two is the threshold; anything unclean resets it to
    #: zero, and sending `terminal_resume` spends it back to zero, so a second terminal
    #: session on the same Run starts counting from nothing. An `int` and not a timestamp:
    #: `tests/unit/test_run_repository_adapter.py`'s closed set of nullable `run` columns is
    #: frozen, and a `NOT NULL` column with a default reaches the same place without joining
    #: it — the same reasoning `worktrees_removed` records above.
    terminal_clean_polls: int = 0
    #: Seconds the Operator had this Run open, batched from the activity endpoint.
    active_seconds: int = 0
    last_opened_at: datetime | None = None
    last_opened_before: datetime | None = None
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
