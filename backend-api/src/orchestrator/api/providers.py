"""Where a request gets its ports.

`deps.py` holds the one credential check and nothing else — `tests/unit/test_bearer_auth.py`
ast-scans that module and fails on any comparison mentioning a token — so the wiring a
feature router needs lives here instead.

One dependency per feature, and each of them owns a transaction: `project_ports` opens a
`SQLAlchemyUnitOfWork`, builds the repository on *that* session, and hands the use case a
scope it only has to `commit()`. Leaving the dependency without a commit rolls back, so a
use case that raised — or a response model that refused the payload — persists nothing.

The adapters themselves are built by `main.py` and read off `app.state`: this module names
no `DATABASE_URL` and no key. `crypto` is a *factory* rather than an adapter, because
`ORCHESTRATOR_SECRET_KEY` is only validated when it is first used (see `main.py`), which
keeps a misconfigured instance startable and `/healthz` answerable.

It does not keep it usable. The factory is called here, on every request that needs these
ports, so an unusable key fails a `GET` exactly as it fails a `POST`. The refusal is a
`ValueError` naming the variable, and this module deliberately does not catch it: it
reaches `api/errors.py` as an unhandled exception, which logs the traceback — variable name
included — and answers a bare `internal server error` problem document. The body says
nothing, because a body that named the misconfigured secret would be the leak.

Nothing here asserts. `python -O` strips `assert`, and an application built without its
ports must answer a problem document, not silently dereference `None`.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import partial
from typing import Annotated, Any

from fastapi import Query, Request

from orchestrator.application.use_cases.activity import ActivityPorts
from orchestrator.application.use_cases.create_run import CreateRunPorts, RunReadPorts
from orchestrator.application.use_cases.harness_readiness import HarnessReadinessPorts
from orchestrator.application.use_cases.harnesses import HarnessPorts
from orchestrator.application.use_cases.history import HistoryPorts
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.application.use_cases.queue import QueuePorts
from orchestrator.application.use_cases.run_files import (
    RunFilesDiffPorts,
    RunFilesPorts,
    RunFilesWritePorts,
)
from orchestrator.application.use_cases.run_views import RunViewPorts
from orchestrator.application.use_cases.signal_run import SignalPorts
from orchestrator.application.use_cases.signals import SignalEffectPorts
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.application.use_cases.terminal import TerminalPorts
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.git import Git
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyGateRecordRepository,
    SQLAlchemyHarnessRepository,
    SQLAlchemyHistoryQuery,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyTemplateVersionRepository,
    SQLAlchemyUnitOfWork,
    open_writer_ports,
)
from orchestrator.infrastructure.db.environment import read_run_environment
from orchestrator.infrastructure.harness.models import model_table
from orchestrator.infrastructure.harness.registry import build_harnesses, build_terminal_env
from orchestrator.infrastructure.process.logs import RealLogReader
from orchestrator.infrastructure.process.runner import RealProcessRunner
from orchestrator.infrastructure.tracing import LangfuseTracer
from orchestrator.infrastructure.workspace.fs import FsWorkspace

#: The attributes `create_app` stores its adapters under.
SESSION_FACTORY = "session_factory"
CRYPTO = "crypto"
GIT = "git"
ENGINE = "engine"
SETTINGS = "settings"


def from_state(request: Request, attribute: str) -> Any:
    """One adapter off `app.state`, or a failure that says which one is missing."""
    value = getattr(request.app.state, attribute, None)
    if value is None:
        raise RuntimeError(
            f"app.state.{attribute} is not set: this application was built without it, "
            "and only main() wires the adapters"
        )
    return value


def git_adapter(request: Request) -> Git | None:
    """The git adapter, read tolerantly rather than through `from_state`.

    Every other adapter here is required, because no route can answer without it. This one
    is not: an application built without it still serves every Project and Repository
    operation, and only the clone check needs it — which then refuses loudly, naming the
    port, rather than this dependency refusing a read that never touches git.
    """
    adapter: Git | None = getattr(request.app.state, GIT, None)
    return adapter


def project_ports(request: Request) -> Iterator[ProjectPorts]:
    """The ports a Project use case runs on, inside one transaction."""
    session_factory = from_state(request, SESSION_FACTORY)
    crypto = from_state(request, CRYPTO)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield ProjectPorts(
            uow=uow,
            projects=SQLAlchemyProjectRepository(uow.session),
            repositories=SQLAlchemyRepositoryRepository(uow.session),
            crypto=crypto(),
            clock=SystemClock(),
            git=git_adapter(request),
            runs=SQLAlchemyRunRepository(uow.session),
            steps=SQLAlchemyStepRunRepository(uow.session),
        )


def template_ports(request: Request) -> Iterator[TemplatePorts]:
    """The ports a Template use case runs on, inside one transaction."""
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield TemplatePorts(
            uow=uow,
            templates=SQLAlchemyTemplateVersionRepository(uow.session),
            clock=SystemClock(),
        )


def harness_ports(request: Request) -> Iterator[HarnessPorts]:
    """The ports a harness use case runs on, inside one transaction."""
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield HarnessPorts(uow=uow, harnesses=SQLAlchemyHarnessRepository(uow.session))


def harness_models(request: Request) -> dict[str, tuple[str, ...]]:
    """The models this instance offers per harness (7.3) — configuration, not a port.

    Its own dependency rather than a field on `HarnessPorts`: nothing here opens a
    transaction, no use case reads it, and it is composed from `Settings` on every request
    precisely so an Operator's `.env` edit reaches the New workflow's select at the next
    restart without a migration (`infrastructure/harness/models.py`).
    """
    return model_table(from_state(request, SETTINGS))


def _required_git(request: Request, needed_by: str) -> Git:
    """`git_adapter`, refusing loudly by name — pre-flight and `create_run` both need it."""
    git = git_adapter(request)
    if git is None:
        raise RuntimeError(
            f"app.state.git is not set: this application was built without it, "
            f"and {needed_by} needs a git port"
        )
    return git


def _preflight_ports(request: Request, uow: SQLAlchemyUnitOfWork, needed_by: str) -> PreflightPorts:
    """The `PreflightPorts` pre-flight and `create_run` (4.4) both run on, over one session
    — `create_run` reuses pre-flight's own resolution rather than building a second one."""
    settings = from_state(request, SETTINGS)
    return PreflightPorts(
        git=_required_git(request, needed_by),
        templates=SQLAlchemyTemplateVersionRepository(uow.session),
        runs=SQLAlchemyRunRepository(uow.session),
        harnesses=SQLAlchemyHarnessRepository(uow.session),
        repositories=SQLAlchemyRepositoryRepository(uow.session),
        projects=SQLAlchemyProjectRepository(uow.session),
        bmad_version=settings.bmad_version,
        max_active_runs=settings.max_active_runs,
        work_dir=settings.work_dir,
    )


def preflight_ports(request: Request) -> Iterator[PreflightPorts]:
    """The ports pre-flight runs on. Writes nothing, but still opens one transaction, the
    way `template_ports` does for its own read-only routes."""
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield _preflight_ports(request, uow, "pre-flight")


def create_run_ports(request: Request) -> Iterator[CreateRunPorts]:
    """The ports `create_run` (4.4) runs on: pre-flight's own, plus what only creation
    writes (`steps`, `engine`), plus a `Tracer` (5.2) so every Run's trace opens.

    `LangfuseTracer(settings)` is built fresh per request rather than read off
    `app.state`: its own client is lazy (built only once a call actually opens a span), and
    `main.py` has no room left for a fourth adapter singleton — see 5.2's Design Notes.
    """
    session_factory = from_state(request, SESSION_FACTORY)
    engine: WorkflowEngine = from_state(request, ENGINE)
    settings = from_state(request, SETTINGS)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield CreateRunPorts(
            preflight=_preflight_ports(request, uow, "create_run"),
            engine=engine,
            steps=SQLAlchemyStepRunRepository(uow.session),
            uow=uow,
            clock=SystemClock(),
            tracer=LangfuseTracer(settings),
        )


def readiness_ports(request: Request) -> Iterator[HarnessReadinessPorts]:
    """The ports `POST /harnesses/{name}/readiness` runs `start` on (SPEC CAP-8).

    `create_run_ports`'s own wiring, over `skip_harness_check=True`: AD-10's carried-forward
    flag, whose one caller this endpoint is — a harness that has never passed readiness can
    still run the readiness Run that would enable it.
    """
    session_factory = from_state(request, SESSION_FACTORY)
    engine: WorkflowEngine = from_state(request, ENGINE)
    settings = from_state(request, SETTINGS)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield HarnessReadinessPorts(
            create_run=CreateRunPorts(
                preflight=_preflight_ports(request, uow, "readiness"),
                engine=engine,
                steps=SQLAlchemyStepRunRepository(uow.session),
                uow=uow,
                clock=SystemClock(),
                skip_harness_check=True,
                tracer=LangfuseTracer(settings),
            ),
            budget_usd=settings.readiness_budget_usd,
            models=settings.readiness_models,
        )


def run_read_ports(request: Request) -> Iterator[RunReadPorts]:
    """The ports `GET /runs`, `GET /runs/{id}` and `GET /runs?view=board` (4.12) read
    through. Writes nothing."""
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield RunReadPorts(
            runs=SQLAlchemyRunRepository(uow.session),
            steps=SQLAlchemyStepRunRepository(uow.session),
            projects=SQLAlchemyProjectRepository(uow.session),
            repositories=SQLAlchemyRepositoryRepository(uow.session),
            gate_records=SQLAlchemyGateRecordRepository(uow.session),
        )


def run_view_ports(request: Request) -> Iterator[RunViewPorts]:
    """The ports the Run detail and the run graph route read through (4.12). The Board
    reads through `run_read_ports` instead — see `application/use_cases/run_views.py`'s own
    module docstring for why it cannot share this one.

    `tracer` (5.2) is what `cost.trace_url` reads through — built fresh per request, the
    same reasoning as `create_run_ports`'s own `LangfuseTracer`.

    `terminal` (6.7) is what the resume command is built through. The registry it carries is
    built with a `RealProcessRunner` of its own, unlike the walker's — AD-14 wants one runner
    able to kill every group *this process started*, and this read starts none: it asks the
    registry for `capabilities.resume` and `resume_command`, neither of which touches a
    process. `build_terminal_env` reads one boolean off `Settings` and no credential at all
    (AD-5)."""
    session_factory = from_state(request, SESSION_FACTORY)
    settings = from_state(request, SETTINGS)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield RunViewPorts(
            runs=SQLAlchemyRunRepository(uow.session),
            steps=SQLAlchemyStepRunRepository(uow.session),
            attempts=SQLAlchemyAttemptRepository(uow.session),
            gate_records=SQLAlchemyGateRecordRepository(uow.session),
            projects=SQLAlchemyProjectRepository(uow.session),
            repositories=SQLAlchemyRepositoryRepository(uow.session),
            logs=RealLogReader(),
            clock=SystemClock(),
            tracer=LangfuseTracer(settings),
            terminal=TerminalPorts(
                env=build_terminal_env(settings),
                harnesses=build_harnesses(settings, RealProcessRunner()),
            ),
        )


def queue_ports(request: Request) -> Iterator[QueuePorts]:
    """The ports `GET /queue` reads through. Writes nothing."""
    session_factory = from_state(request, SESSION_FACTORY)
    engine: WorkflowEngine = from_state(request, ENGINE)
    settings = from_state(request, SETTINGS)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield QueuePorts(
            engine=engine,
            runs=SQLAlchemyRunRepository(uow.session),
            steps=SQLAlchemyStepRunRepository(uow.session),
            clock=SystemClock(),
            max_active_runs=settings.max_active_runs,
        )


def history_ports(request: Request) -> Iterator[HistoryPorts]:
    """The ports `GET /steps` reads through (7.5). Writes nothing.

    `tracer` is built fresh per request, the same reasoning `run_view_ports` gives for its
    own: it answers a URL by string format and opens nothing. The link it builds is the
    *Run's* trace, because nothing stores a per-attempt trace id — see
    `application/use_cases/history.py`'s own docstring.
    """
    session_factory = from_state(request, SESSION_FACTORY)
    settings = from_state(request, SETTINGS)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield HistoryPorts(
            history=SQLAlchemyHistoryQuery(uow.session), tracer=LangfuseTracer(settings)
        )


def run_files_ports(request: Request) -> Iterator[RunFilesPorts]:
    """The ports `GET /runs/{id}/files` reads through (6.2). Writes nothing.

    `workspace` is `FsWorkspace` itself — a factory, not an instance — the same "port is
    the class" shape `infrastructure/dbos/startup.py` already wires `StepPorts.workspace`
    with: the use case cannot root one until it has read the Run's own `worktree_path`.
    """
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield RunFilesPorts(runs=SQLAlchemyRunRepository(uow.session), workspace=FsWorkspace)


def run_files_write_ports(request: Request) -> Iterator[RunFilesWritePorts]:
    """The ports `PUT /runs/{id}/files` writes through (6.3): `run_files_ports`'s own shape,
    plus `Git` to stage and commit the Operator's edit, a `GateRecordRepository` for the
    `spec_edit` line, a `Clock`, and the `UnitOfWork` itself so the use case can `commit()`.
    """
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield RunFilesWritePorts(
            runs=SQLAlchemyRunRepository(uow.session),
            workspace=FsWorkspace,
            git=_required_git(request, "run_files"),
            records=SQLAlchemyGateRecordRepository(uow.session),
            clock=SystemClock(),
            uow=uow,
        )


def activity_ports(request: Request) -> Iterator[ActivityPorts]:
    """The ports `GET/POST /runs/{id}/activity` reads and writes through (8.2)."""
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield ActivityPorts(runs=SQLAlchemyRunRepository(uow.session), uow=uow)


def run_files_diff_ports(
    request: Request, diff: Annotated[bool, Query()] = False
) -> Iterator[RunFilesDiffPorts | None]:
    """The ports `GET /runs/{id}/files?diff=1` reads through (6.6). Writes nothing.

    No `Workspace`: the diff is `Git`'s own answer over the worktree, and the scope gate is
    the park's recorded hit list rather than the spec folder — see
    `application/use_cases/run_files.py`'s own docstring for why.

    **It reads the mode's own query parameter, and it has to.** FastAPI resolves every
    dependency a handler declares, on every request to it — so a dependency that opened a
    session unconditionally would make the two reads that share this route (the file and the
    tree) require adapters they have never needed, and would break every existing test that
    overrides only `run_files_ports`. That is the same trap `application/use_cases/
    run_views.py` documents for `board_view`. Answering `None` for the modes that did not
    ask is what keeps this route's other two answers exactly as they were.
    """
    if not diff:
        yield None
        return
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield RunFilesDiffPorts(
            runs=SQLAlchemyRunRepository(uow.session),
            steps=SQLAlchemyStepRunRepository(uow.session),
            attempts=SQLAlchemyAttemptRepository(uow.session),
            records=SQLAlchemyGateRecordRepository(uow.session),
            git=_required_git(request, "run_files"),
        )


def signal_effect_ports(request: Request) -> Iterator[SignalEffectPorts]:
    """The ports `handle_signal` (4.9) runs on: `signal_run`'s own writers, plus `cancel`'s
    cleanup — a `Git`, a `ProcessRunner`, `WORK_DIR`, and one Run's environment, read the
    same way `infrastructure/dbos/walker.py` reads it for an executor (4.8)."""
    session_factory = from_state(request, SESSION_FACTORY)
    engine: WorkflowEngine = from_state(request, ENGINE)
    settings = from_state(request, SETTINGS)
    with open_writer_ports(session_factory) as writers:
        yield SignalEffectPorts(
            signal=SignalPorts(writers=writers, engine=engine),
            git=_required_git(request, "signals"),
            process=RealProcessRunner(),
            work_dir=settings.work_dir,
            read_environment=partial(read_run_environment, session_factory, settings.bmad_version),
        )
