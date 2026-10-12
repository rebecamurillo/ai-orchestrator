"""Where a request gets its ports.

`deps.py` holds the one credential check only — `tests/unit/test_bearer_auth.py` ast-scans
that module and fails on any token comparison — so feature wiring lives here instead.

One dependency per feature, each owning a transaction: yielding without `commit()` rolls
back, so a use case that raised — or a response model that refused the payload — persists
nothing.  Adapters are read off `app.state`; this module names no `DATABASE_URL` and no key.

`crypto` is a factory, not a singleton: `ORCHESTRATOR_SECRET_KEY` is validated on first use,
so a misconfigured key refuses the first request that needs it (a `ValueError` → bare
`internal server error` — the body names nothing, because naming the variable would be the
leak) rather than failing startup.

At the 400-line cap (`test_source_limits.py`) this module splits rather than trims: the
`app.state` attribute names and accessors live in `providers_base.py`, the run-files feature
in `providers_run_files.py`, trajectories in `providers_trajectories.py`. `__all__` below
re-exports what the frozen router tests and `routers/run_files.py` import from here.

Nothing here asserts. `python -O` strips `assert`.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import partial
from typing import Annotated

from fastapi import Depends, Query, Request

from orchestrator.api.providers_base import (
    CRYPTO,
    ENGINE,
    GIT,
    SESSION_FACTORY,
    SETTINGS,
    from_state,
    git_adapter,
    required_git,
)
from orchestrator.api.providers_run_files import (
    run_files_diff_ports,
    run_files_ports,
    run_files_write_ports,
)
from orchestrator.application.use_cases.activity import ActivityPorts
from orchestrator.application.use_cases.create_run import CreateRunPorts, RunReadPorts
from orchestrator.application.use_cases.harness_probe import HarnessProbePorts
from orchestrator.application.use_cases.harness_readiness import HarnessReadinessPorts
from orchestrator.application.use_cases.harnesses import HarnessPorts
from orchestrator.application.use_cases.history import HistoryPorts
from orchestrator.application.use_cases.open_run import OpenRunPorts
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.application.use_cases.queue import QueuePorts
from orchestrator.application.use_cases.repositories import InitRepositoryPorts
from orchestrator.application.use_cases.run_views import RunViewPorts
from orchestrator.application.use_cases.signal_run import SignalPorts
from orchestrator.application.use_cases.signals import SignalEffectPorts
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.application.use_cases.terminal import TerminalPorts
from orchestrator.domain.ports.engine import WorkflowEngine
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
from orchestrator.infrastructure.notify import build_notifier
from orchestrator.infrastructure.process.logs import RealLogReader, log_secrets
from orchestrator.infrastructure.process.runner import RealProcessRunner
from orchestrator.infrastructure.skill_catalog import FsSkillCatalog, manifest_path
from orchestrator.infrastructure.tracing import build_tracer

#: Re-exports: the frozen router tests and `routers/run_files.py` import these names from
#: here; the wiring itself lives in the capped-module siblings named in the docstring.
__all__ = [
    "GIT",
    "run_files_diff_ports",
    "run_files_ports",
    "run_files_write_ports",
]


def project_ports(request: Request) -> Iterator[ProjectPorts]:
    """The ports a Project use case runs on, inside one transaction."""
    session_factory = from_state(request, SESSION_FACTORY)
    crypto = from_state(request, CRYPTO)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield ProjectPorts(
            init_template=from_state(request, SETTINGS).init_template,
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


def harness_probe_ports(request: Request) -> HarnessProbePorts:
    """The ports `GET /harnesses/{name}/probe` runs on (story 2-1).

    Builds the harness registry fresh per request — no DB session, no transaction.
    `ProcessRunner` is constructed but unused by `probe()`: each adapter shells its script
    via `subprocess.run` directly, so the runner is only here because `build_harnesses`
    requires it.
    """
    settings = from_state(request, SETTINGS)
    harnesses = build_harnesses(settings, RealProcessRunner())
    return HarnessProbePorts(harnesses=harnesses)


def harness_models(request: Request) -> dict[str, tuple[str, ...]]:
    """The models this instance offers per harness (7.3) — configuration, not a port.

    Its own dependency rather than a field on `HarnessPorts`: nothing here opens a
    transaction, no use case reads it, and it is composed from `Settings` on every request
    precisely so an Operator's `.env` edit reaches the New workflow's select at the next
    restart without a migration (`infrastructure/harness/models.py`).
    """
    return model_table(from_state(request, SETTINGS))


def _preflight_ports(request: Request, uow: SQLAlchemyUnitOfWork, needed_by: str) -> PreflightPorts:
    """The `PreflightPorts` pre-flight and `create_run` (4.4) both run on, over one session
    — `create_run` reuses pre-flight's own resolution rather than building a second one."""
    settings = from_state(request, SETTINGS)
    return PreflightPorts(
        git=required_git(request, needed_by),
        templates=SQLAlchemyTemplateVersionRepository(uow.session),
        runs=SQLAlchemyRunRepository(uow.session),
        harnesses=SQLAlchemyHarnessRepository(uow.session),
        repositories=SQLAlchemyRepositoryRepository(uow.session),
        projects=SQLAlchemyProjectRepository(uow.session),
        skill_catalog=FsSkillCatalog(manifest_path(settings.agent_home)),
        bmad_version=settings.bmad_version,
        max_active_runs=settings.max_active_runs,
        work_dir=settings.work_dir,
        harness_registry=build_harnesses(settings, RealProcessRunner()),
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

    `build_tracer(settings)` is built fresh per request rather than read off
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
            tracer=build_tracer(settings),
        )


def readiness_ports(request: Request) -> Iterator[HarnessReadinessPorts]:
    """The ports `POST /harnesses/{name}/readiness` runs `start` on (SPEC CAP-8).

    `create_run_ports`'s own wiring.  The `skip_harness_check=True` exemption (AD-10) that
    bypassed the old `enabled`-flag check is removed here (story 2-2, 2026-09-16): a
    correctly-installed harness returns `ok=True` from the live probe regardless of whether
    it has ever passed a readiness Run, so the exemption is both wrong (it would now bypass
    the probe, not the `enabled` check) and unnecessary.  `skip_harness_check` stays on
    `CreateRunPorts` reserved for epic 5.
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
                tracer=build_tracer(settings),
            ),
            budget_usd=settings.readiness_budget_usd,
            template_name=settings.readiness_template,
            models=settings.readiness_models,
        )


def init_repository_ports(
    request: Request, ports: Annotated[CreateRunPorts, Depends(create_run_ports)]
) -> InitRepositoryPorts:
    """`create_run`'s own ports plus `INIT_TEMPLATE` (AD-20), for `POST /repositories/{id}/
    init`. A sub-dependency rather than a second copy of `create_run_ports`' wiring, so the
    action runs in exactly the transaction `POST /runs` does; the *only* thing this adds is
    the configured Template name, read here because the composition root is the one place
    `Settings` is read (AD-2)."""
    return InitRepositoryPorts(
        create_run=ports, template_name=from_state(request, SETTINGS).init_template
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
    same reasoning as `create_run_ports`'s own `build_tracer` call.

    `terminal` (6.7): built with `build_terminal_env` and `build_harnesses` — neither starts
    a process (AD-14), and `build_terminal_env` reads no credential (AD-5).

    `harness_is_resumable` (story 3-4): shares the same `build_harnesses` call already
    made for `terminal`, extracted to a local variable so neither call is duplicated."""
    session_factory = from_state(request, SESSION_FACTORY)
    settings = from_state(request, SETTINGS)
    harnesses = build_harnesses(settings, RealProcessRunner())
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield RunViewPorts(
            runs=SQLAlchemyRunRepository(uow.session),
            steps=SQLAlchemyStepRunRepository(uow.session),
            attempts=SQLAlchemyAttemptRepository(uow.session),
            gate_records=SQLAlchemyGateRecordRepository(uow.session),
            projects=SQLAlchemyProjectRepository(uow.session),
            repositories=SQLAlchemyRepositoryRepository(uow.session),
            logs=RealLogReader(log_secrets(settings)),
            clock=SystemClock(),
            tracer=build_tracer(settings),
            terminal=TerminalPorts(
                env=build_terminal_env(settings),
                harnesses=harnesses,
            ),
            harness_is_resumable=lambda name: (
                name in harnesses and harnesses[name].capabilities.resume
            ),
            git=git_adapter(request),
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
            history=SQLAlchemyHistoryQuery(uow.session), tracer=build_tracer(settings)
        )


def activity_ports(request: Request) -> Iterator[ActivityPorts]:
    """The ports `GET/POST /runs/{id}/activity` reads and writes through (8.2)."""
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield ActivityPorts(runs=SQLAlchemyRunRepository(uow.session), uow=uow)


def open_run_ports(
    request: Request, opened: Annotated[bool, Query()] = False
) -> Iterator[OpenRunPorts | None]:
    """The ports `open_run` writes through (8.3): `runs`, `uow`, and a `Clock`.

    Reads `?opened` itself and yields `None` when absent — same pattern as
    `run_files_diff_ports`'s `?diff` — so the dependency only opens a session on demand.
    """
    if not opened:
        yield None
        return
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield OpenRunPorts(
            runs=SQLAlchemyRunRepository(uow.session),
            uow=uow,
            clock=SystemClock(),
        )


def signal_effect_ports(request: Request) -> Iterator[SignalEffectPorts]:
    """The ports `handle_signal` (4.9) runs on: `signal_run`'s own writers, plus `cancel`'s
    cleanup — a `Git`, a `ProcessRunner`, `WORK_DIR`, and one Run's environment, read the
    same way `infrastructure/dbos/walker.py` reads it for an executor (4.8).

    `harness_is_resumable` and `latest_attempt_for_run` are injected into `SignalPorts` so
    that `_check_mode` can validate `mode="session"` without the application layer importing
    infrastructure adapters (AD-2, story 3-3).

    `preflight_uow` is a read-only session for the Probe re-read the `start` signal runs
    before enqueueing a saved Run (story 5-3, AD-13). It is a separate session from the
    writers' session so the held-branch check sees the latest committed state of other Runs.
    The same pattern `create_run_ports` uses via `_preflight_ports`.
    """
    session_factory = from_state(request, SESSION_FACTORY)
    engine: WorkflowEngine = from_state(request, ENGINE)
    settings = from_state(request, SETTINGS)
    harnesses = build_harnesses(settings, RealProcessRunner())
    with SQLAlchemyUnitOfWork(session_factory) as preflight_uow:
        with open_writer_ports(session_factory, notifier=build_notifier(settings)) as writers:
            yield SignalEffectPorts(
                signal=SignalPorts(
                    writers=writers,
                    engine=engine,
                    harness_is_resumable=lambda name: (
                        name in harnesses and harnesses[name].capabilities.resume
                    ),
                    latest_attempt_for_run=writers.attempts.latest_for_run,
                    preflight=_preflight_ports(request, preflight_uow, "signals"),
                ),
                git=required_git(request, "signals"),
                process=RealProcessRunner(),
                work_dir=settings.work_dir,
                read_environment=partial(
                    read_run_environment, session_factory, settings.bmad_version
                ),
            )
