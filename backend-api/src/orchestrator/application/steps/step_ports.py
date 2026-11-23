"""`StepPorts`, split from `context.py` for its line cap; its docstring explains the fields."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from orchestrator.application.use_cases.run_records import RecordWrites
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.harness import Harness, HarnessEnv
from orchestrator.domain.ports.logs import LogReader
from orchestrator.domain.ports.process import ProcessRunner
from orchestrator.domain.ports.protected_paths import ProtectedPaths
from orchestrator.domain.ports.skill_catalog import SkillCatalog
from orchestrator.domain.ports.step_log import StepLog
from orchestrator.domain.ports.tracer import Tracer

if TYPE_CHECKING:  # context.py imports this module at runtime; a runtime import back is a cycle
    from orchestrator.application.steps.context import (
        AttemptWrites,
        FactsWrites,
        RunAnalysis,
        RunEnvironment,
        SpendWrites,
        WorkspaceFactory,
    )


@dataclass(frozen=True)
class StepPorts:
    """The outside world an executor is allowed to reach, built in the composition root."""

    git: Git
    clock: Clock
    #: `WORK_DIR`: the root every worktree and every log file of every Run lives under.
    work_dir: str
    #: `None` until a kind that runs a command needs it (4.7 registers the first one).
    process: ProcessRunner | None = None
    #: `None` until a kind that reads or writes the worktree needs it (4.7 registers the
    #: first one). A factory rather than an instance — see the module docstring.
    workspace: WorkspaceFactory | None = None
    #: The Run this row belongs to, as the walker read it (4.8). `None` in a process that
    #: never resolved one, which is every unit test not about a git kind.
    run_env: RunEnvironment | None = None
    #: AD-17's frozen-anchor rule. `None` throughout Epic 4 — the port is the seam Epic 5
    #: fills; `domain/ports/protected_paths.py` says why that is not a green check.
    protected_paths: ProtectedPaths | None = None
    #: `None` until a caller wires a real one (5.2). `run_row` degrades to "no span opened"
    #: when unset — every frozen `StepPorts(...)` construction predating this story keeps
    #: working unchanged; 5.4's agent executor reaches this the same way, through
    #: `context.ports.tracer`, so `WalkPorts` itself needs no `Tracer` of its own (AD-11).
    tracer: Tracer | None = None
    #: The harness registry, keyed by the name a Template writes (AD-10). `None` outside a
    #: process that wired one, which is every unit test not about the `agent` kind.
    harnesses: Mapping[str, Harness] | None = None
    #: What builds one attempt's harness environment (AD-5). A port, so `application/` never
    #: reaches `infrastructure/harness/env.py` or the `Settings` it reads.
    harness_env: HarnessEnv | None = None
    #: One unit of work per attempt write (AD-8). The `agent` kind is the only executor that
    #: writes at all, and it writes only through `WriterPorts.attempts`.
    attempt_writes: AttemptWrites | None = None
    #: How the walker reads the tail of a failed `verify` row's log (SPEC CAP-12, 5.5).
    #: `None` in every process that wired none, which degrades to "no lines resolved" — the
    #: same "no facts, no append" the executor already has to handle.
    logs: LogReader | None = None
    #: The attempt's own spend scope (5.7). `None` skips the budget read — see the module
    #: docstring's "degrades like `tracer`" — rather than raising like `attempt_writes`.
    spend_writes: SpendWrites | None = None
    #: `None` records no facts, the same way `None` skips the budget read above.
    facts_writes: FactsWrites | None = None
    skill_catalog: SkillCatalog | None = None
    record_writes: RecordWrites | None = None
    #: `None` makes a `metrics.analyse` row read `analysis failed`, never an error.
    analysis: RunAnalysis | None = None
    #: `None` writes no log.
    step_log: StepLog | None = None
