"""What an executor is handed and what it must be (AD-9): `StepContext` and `StepExecutor`.

One kind, one module, one protocol. An executor is a pure function over its context: it
reads the row the planner recorded, does the kind's work through the ports it was given,
and returns a `StepResult`. It never writes a status, never reaches a repository, and never
imports `infrastructure` — `StepPorts` is built once in `main.py` and travels here (AD-2,
AD-8).

`StepContext` is the spine's own field list. Two of them carry a rule:

- **`with_resolved` is the row's, not the Template's.** The planner resolved every
  expression before the Run started (AD-7); an executor that re-read a Template would be
  re-planning mid-Run.
- **`resume_signal` is a `GateRecord`, not a `Signal`.** AD-9 puts a signal's worktree
  effects in the resumed row's executor, and the record is what `signal_run` committed — a
  durable row rather than a message the engine happened to carry.

`StepPorts` holds what the executors can reach today, and grows with them. Every field is a
port or a plain value, so a unit test builds one from the shared fakes.

**`workspace` is a factory, not an instance.** `Git`, `Clock` and `process` are the same
object for every row of every Run. A `Workspace` is rooted at `run.worktree_path`, a fact of
one Run, so `StepPorts` — built once, before any Run exists — cannot hold a rooted instance
without holding a stale one for every Run after the first. `StepPorts.workspace(ctx.cwd)`
builds the one the current row needs, on demand, from the root the walker already read.

**`run_env` is resolved by the walker, not fetched by the executor.** AD-9 closes
`StepContext`'s field list, and an executor needs facts the row cannot carry: where this
Repository's clone lives, its `install_command`, its default branch, the worktrees this Run
has made. `ports` is the field AD-9 leaves open, so the walker's `attempt_row` step reads
those once, before the executor runs, and hands them over as a frozen `RunEnvironment`
inside `StepPorts`. The executor reads a value and never a repository, which is AD-8.

**Epic 5's fields are the same move, one layer out.** `harnesses`, `harness_env`,
`attempt_writes` and `logs` are what the `agent` kind and the walker need and no other kind
has. All are ports or plain callables, all are built once in the composition root, and all
default to `None` so every `StepPorts(...)` written before them keeps working —
`tests/unit/test_step_executor_registry.py` and the walk's own tests still construct one
from `git`, `clock` and `work_dir` alone. `RunEnvironment` grew the same way: the `Run`
entity, the Project's own context and variables, `test_globs` and the verify failure are
all facts `read_run_environment` or the walker already had a session open for.

**The three questions at the end are how an executor knows which re-dispatch it is.** AD-9
closes `StepContext`'s field list, so `retrying`, `operator_retry` and `redispatched` read
the fields already there rather than a new one.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.harness import Harness, HarnessEnv
from orchestrator.domain.ports.logs import LogReader
from orchestrator.domain.ports.process import ProcessRunner
from orchestrator.domain.ports.protected_paths import ProtectedPaths
from orchestrator.domain.ports.repositories import AttemptRepository
from orchestrator.domain.ports.tracer import Tracer
from orchestrator.domain.ports.workspace import Workspace
from orchestrator.domain.values import StepResult, Worktree

#: What `StepPorts.workspace` is: a `Workspace` rooted at whichever path the caller names.
WorkspaceFactory = Callable[[str | None], Workspace]

#: What `StepPorts.attempt_writes` is: one scope's `WriterPorts`, opened and closed around a
#: single commit. The `agent` executor writes an attempt three times in three units of work
#: (AD-8), and each of them opens one of these — never a session held across a dispatch that
#: runs for ninety minutes.
AttemptWrites = Callable[[], AbstractContextManager[WriterPorts]]

#: The directory a Repository's base clone lives in, under its Project's (AD-14). The same
#: word `use_cases/clone_check.py` uses, because it is the same directory.
BASE_DIRECTORY = "base"

#: The directory every worktree of a Repository lives under (AD-14). A `/` in a branch name
#: becomes a directory level, which is what `Path` does with it anyway.
WORKTREES_DIRECTORY = "wt"


@dataclass(frozen=True)
class ProjectContext:
    """The Project facts a dispatch hands to a harness process (AD-5, FR-14).

    `env_vars` is *decrypted*: `read_run_environment` turns `project.env_vars_enc` into
    plaintext through the `Crypto` port, which is `domain/ports/crypto.py`'s "only when a
    Run is about to hand the value to a harness process". It is never written to
    `step_run.with_resolved`, never logged and never returned by an endpoint.
    """

    context_text: str = ""
    context_paths: tuple[str, ...] = ()
    #: `repr=False` is the docstring's "never logged", made mechanical: a dataclass prints
    #: every field by default, and this one holds plaintext secrets — one `structlog` binding
    #: or one traceback frame carrying the value would be the leak AD-5 forbids.
    env_vars: Mapping[str, str] = field(default_factory=dict, repr=False)
    log_prompt_content: bool = False


@dataclass(frozen=True)
class VerifyFailure:
    """Why the `verify` row sent this Story back, as the walker read it (FR-10, AD-9).

    A value and not a handle, for the reason every other field of `RunEnvironment` is one:
    the row that failed is a different row, its attempt is a different attempt, and an
    executor that could ask a repository for either would be reading state AD-8 says only
    the walker holds. `walk._context` resolves it once, before the executor runs.
    """

    #: The `verify` row's own resolved command, as the Operator would re-run it.
    command: str
    #: What it exited with; `None` when it was sent back before an attempt recorded one.
    exit_code: int | None
    #: The last lines of its log, oldest first, as `LogReader.tail` answered them.
    log_tail: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunEnvironment:
    """One Run's own facts, as the walker read them just before this row ran.

    A snapshot, not a handle: an executor cannot ask it a second question and cannot write
    through it. Everything here is a Project/Repository column the plan was built from, or a
    Run column an earlier row committed — so a row always sees what the row before it left.
    """

    run_id: UUID
    project_slug: str
    repository_slug: str
    repository_url: str
    default_branch: str
    #: `""` when the Repository declares none — `git.worktree` then runs nothing.
    install_command: str
    #: The `BMAD_VERSION` this instance runs (AD-16), for `bmad.install`.
    bmad_version: str
    #: The Run input every dev-loop Template declares, or `None` (`repo-init@1` has none).
    spec_folder: str | None
    #: Every worktree this Run has made so far, as `run.worktrees[]` stands now.
    worktrees: tuple[Worktree, ...] = ()
    #: Every compare URL this Run has recorded so far (`initiative@1` records one per epic).
    compare_urls: tuple[str, ...] = ()
    #: `run.accepted_paths` — files an earlier `continue` let through (AD-9).
    accepted_paths: tuple[str, ...] = ()
    #: The Run itself, for the three things that need the entity and not a column of it:
    #: `env_for(run=…)`, `Tracer.attempt_span(run, …)` and `budget_usd - spend_usd`. `None`
    #: in every `RunEnvironment(...)` written before 5.4.
    run: Run | None = None
    #: The Project's own context and variables, as the harness receives them (AD-5). A
    #: factory, not one instance built at class-definition time: a shared default would give
    #: every `RunEnvironment` that omits the field the same `env_vars` mapping.
    project: ProjectContext = field(default_factory=ProjectContext)
    #: `repository.test_globs` — what AD-17's frozen test set is computed from.
    test_globs: tuple[str, ...] = ()
    #: Why the `verify` row redispatched to this one, or `None` — which is every row that
    #: was not sent back, and every walker built before 5.5 resolved one (FR-10).
    verify_failure: VerifyFailure | None = None

    def base_dir(self, work_dir: str) -> Path:
        """`{work_dir}/{project.slug}/{repository.slug}/base` — the one layout (AD-14)."""
        return Path(work_dir) / self.project_slug / self.repository_slug / BASE_DIRECTORY

    def worktree_dir(self, work_dir: str, branch: str) -> Path:
        """`{work_dir}/{project.slug}/{repository.slug}/wt/{branch}` (AD-14)."""
        root = Path(work_dir) / self.project_slug / self.repository_slug / WORKTREES_DIRECTORY
        return root / branch

    def worktree_at(self, path: str | None) -> Worktree | None:
        """The recorded worktree this Run is standing in, or `None` before there is one."""
        return next((entry for entry in self.worktrees if entry.path == path), None)


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


@dataclass(frozen=True)
class StepContext:
    """Everything the executor of one row needs, and nothing it could use to write state."""

    row: StepRun
    with_resolved: dict[str, Any]
    #: `run.worktree_path` — `None` before `git.worktree` has made one (4.8).
    cwd: str | None
    #: The commit the row's Story frame started at, or `None` outside a frame (Epic 5).
    frame_start_sha: str | None
    #: The attempt before this one at the same row, or `None` for a row's first attempt.
    previous_attempt: Attempt | None
    attempt: Attempt
    #: The gate record of the Operator signal that resumed this row, or `None` (AD-9).
    resume_signal: GateRecord | None
    ports: StepPorts


@runtime_checkable
class StepExecutor(Protocol):
    """One step kind's whole behaviour: context in, result out, no status written."""

    def execute(self, ctx: StepContext) -> StepResult:
        """Do the kind's work and report what the row reached."""
        ...


def log_path(ctx: StepContext) -> Path:
    """`/work/logs/{run_id}/{seq:03d}-{attempt_n}.log` — one path, computed the same way

    by every kind that starts a process. Nothing here reads the filesystem: the path is a
    pure function of the Run, the row and the attempt, so any kind can compute it before
    `ProcessRunner.start` creates the file it names.
    """
    return (
        Path(ctx.ports.work_dir)
        / "logs"
        / str(ctx.attempt.run_id)
        / f"{ctx.row.seq:03d}-{ctx.attempt.n}.log"
    )


#: What an unset port on `StepPorts` means: a composition-root wiring bug, not a row's. The
#: three git kinds need all of them, so the refusal is here rather than six times over.
NO_ENVIRONMENT = "StepPorts.run_env is not set: a git kind needs the Run's environment"
NO_RUNNER = "StepPorts.process is not set: this kind needs a ProcessRunner"
NO_WORKSPACE = "StepPorts.workspace is not set: this kind needs a Workspace"
NO_HARNESSES = "StepPorts.harnesses is not set: the agent kind needs the harness registry"
NO_HARNESS_ENV = "StepPorts.harness_env is not set: the agent kind needs an environment builder"
NO_ATTEMPT_WRITES = "StepPorts.attempt_writes is not set: the agent kind needs a unit of work"
#: What a `RunEnvironment` carrying no `Run` means: the reader that built it is out of date.
NO_RUN = "RunEnvironment.run is not set: the agent kind needs the Run it dispatches for"
#: What a git kind says when it is reached before `git.worktree` has made a worktree.
NO_WORKTREE = "no worktree: {path} runs before git.worktree"

#: The `gate_record.event` an Operator's *Retry* leaves (AD-13), as `signal_run` wrote it.
RETRY_EVENT = "retry"


def require_env(ctx: StepContext) -> RunEnvironment:
    """The Run's environment, or the wiring bug that it was never resolved."""
    if ctx.ports.run_env is None:
        raise RuntimeError(NO_ENVIRONMENT)
    return ctx.ports.run_env


def require_process(ctx: StepContext) -> ProcessRunner:
    """The process runner, or the wiring bug that none was built."""
    if ctx.ports.process is None:
        raise RuntimeError(NO_RUNNER)
    return ctx.ports.process


def require_workspace(ctx: StepContext, root: str | None) -> Workspace:
    """A `Workspace` rooted where the caller says, or the wiring bug that none was built."""
    if ctx.ports.workspace is None:
        raise RuntimeError(NO_WORKSPACE)
    return ctx.ports.workspace(root)


def require_harnesses(ctx: StepContext) -> Mapping[str, Harness]:
    """The harness registry, or the wiring bug that none was built."""
    if ctx.ports.harnesses is None:
        raise RuntimeError(NO_HARNESSES)
    return ctx.ports.harnesses


def require_harness_env(ctx: StepContext) -> HarnessEnv:
    """The environment builder, or the wiring bug that none was bound."""
    if ctx.ports.harness_env is None:
        raise RuntimeError(NO_HARNESS_ENV)
    return ctx.ports.harness_env


def require_attempt_writes(ctx: StepContext) -> AttemptWrites:
    """How an attempt write opens its own unit of work, or the wiring bug that it cannot."""
    if ctx.ports.attempt_writes is None:
        raise RuntimeError(NO_ATTEMPT_WRITES)
    return ctx.ports.attempt_writes


def require_run(ctx: StepContext) -> Run:
    """The Run this row belongs to, or the wiring bug that the reader did not carry it."""
    run = require_env(ctx).run
    if run is None:
        raise RuntimeError(NO_RUN)
    return run


def require_cwd(ctx: StepContext) -> Path:
    """The worktree this row runs in — a row reached before `git.worktree` has none."""
    if ctx.cwd is None:
        raise RuntimeError(NO_WORKTREE.format(path=ctx.row.path))
    return Path(ctx.cwd)


def resolved_text(resolved: Mapping[str, Any], key: str) -> str:
    """One resolved key as a string; an absent, null or empty value is `""` either way.
    Here rather than in `steps/agent.py` because the tail reads the same row the dispatch
    does, and the dependency between the two runs one way."""
    return str(resolved.get(key) or "").strip()


def committed(ctx: StepContext, write: Callable[[AttemptRepository], None]) -> None:
    """One attempt write, in its own scope and transaction; `AttemptRepository` only (AD-8)."""
    with require_attempt_writes(ctx)() as writers, writers.uow:
        write(writers.attempts)
        writers.uow.commit()


def retrying(ctx: StepContext) -> bool:
    """Whether this attempt is the Template's own `retry` firing again (AD-9, FR-16).

    An automatic re-queue only ever follows `error` (a retry) or `done` (a verify
    redispatch), and every Operator resume carries a `resume_signal` — so "no signal, and
    the attempt before this one ended `error`" is nearly a retry, and `end_sha` is the rest
    of it. A backend killed mid-dispatch leaves exactly that shape too: `start_attempt`
    closes the interrupted attempt `error` and the walk restarts with no signal at all.
    `end_sha` is written only by the tail, so it alone means "the dispatch came back" —
    the same discriminator `agent.py::_orphan_control` uses, for the same reason `ended_at`
    cannot be one. Without it a crash recovery would resume the killed session with a retry
    prompt and never be counted against `retry_count`, which AD-9 forbids.
    """
    previous = ctx.previous_attempt
    return (
        ctx.resume_signal is None
        and previous is not None
        and previous.status == "error"
        and previous.end_sha is not None
    )


def operator_retry(ctx: StepContext) -> bool:
    """Whether a person sent this row *Retry* from the stop it parked on (AD-13, §4.6).

    The other half of "run this row again". `misconfigured` — `ambiguous story file` above
    all — is never re-executed automatically (AD-9), so an Operator signal is the only way
    such a row ever runs a second time, and the prepare phase has to recognise it.
    """
    signal = ctx.resume_signal
    return signal is not None and signal.event == RETRY_EVENT


def redispatched(ctx: StepContext) -> bool:
    """Whether this attempt is a `verify` row sending the Story back (FR-10, AD-9).

    The observable form of "the row's redispatch counter went up": an agent row reaches
    `done` before verify can fail it, so a predecessor that finished plus a counter above
    zero is a redispatch. It stays right when a retry follows a redispatch — that attempt's
    predecessor is `error`, so this answers `False` and nothing is appended twice.
    """
    previous = ctx.previous_attempt
    return (
        ctx.resume_signal is None
        and previous is not None
        and previous.status == "done"
        and ctx.row.redispatch_count > 0
    )
