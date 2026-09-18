"""Composition root: the only module that wires adapters into ports.

The durable engine is launched here too (Operations): `main()` builds it — no connection —
names it as the engine this process serves with, and `run_migrations` launches it after the
schema and the seeds, before uvicorn binds. `infrastructure/dbos/startup.py` says why the
launch lives inside that one name and not beside it. Everything else is a FastAPI
application: the public `/healthz`, and every feature router mounted under `/api/v1` behind
the one bearer dependency (AD-4).

`create_app` performs no I/O, and it is `main()` — never `create_app` — that wires
`alembic upgrade head` in as the application's start-up step. Why it is done that way, and
what it guarantees, is stated once in
`orchestrator.infrastructure.db.migrations`; this module is where it is wired.

The adapters follow the same split. `main()` builds the engine and the session factory —
neither opens a connection — and stores them on `app.state` for `api/providers.py` to read
per request. The `Crypto` adapter is passed as a *factory* rather than as an instance,
because `FernetCrypto` validates `ORCHESTRATOR_SECRET_KEY` strictly and the contract's
placeholder is not a Fernet key: `tests/unit/test_logging.py` and
`tests/unit/test_migrations.py` call `main()` with exactly those placeholders. Deferring
the construction means a misconfigured instance still starts and still answers `/healthz`.
What it does not do is serve `/api/v1/projects`: `api/providers.py` builds the adapter for
every request that needs a Project port, so a *read* fails as surely as a write, and it
fails the same way — a bare `internal server error` problem document, with the message
naming `ORCHESTRATOR_SECRET_KEY` in the log and nothing of it in the body. The operator
sees a 500 and finds the reason in `docker compose logs backend-api`.

This module's own `run_migrations` wraps `infrastructure.db.migrations.run_migrations`
with the shipped-Templates seed (SPEC CAP-3), because `tests/unit/test_migrations.py`
proves "migrate before bind" by replacing `main.run_migrations` wholesale. Seeding shares
that one name so the same replacement keeps it, too, out of a unit test's reach — a test
that patched only the alembic step would leave the seed to run for real, against no
database at all, which AD-18 forbids. `infrastructure.db.migrations.run_migrations` stays
the one statement of *when the schema migrates*; this module only orders the two steps.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import cache
from importlib.metadata import PackageNotFoundError, version

import structlog
import uvicorn
from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from orchestrator.api.deps import require_bearer
from orchestrator.api.errors import UNAUTHORIZED_RESPONSE, install_error_handlers
from orchestrator.api.routers import (
    clone_check,
    graph,
    graph_text,
    harness_probe,
    harness_readiness,
    harnesses,
    history,
    ping,
    projects,
    queue,
    repositories,
    repository_init,
    run,
    run_activity,
    run_attempts,
    run_detail,
    run_files,
    runs,
    signals,
    start_run,
    step_detail,
    templates,
    trajectories,
)
from orchestrator.application.use_cases.templates import SeedResult, TemplatePorts, seed_shipped
from orchestrator.domain.ports.crypto import Crypto
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.git import Git
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.crypto import FernetCrypto
from orchestrator.infrastructure.db import (
    SQLAlchemyTemplateVersionRepository,
    SQLAlchemyUnitOfWork,
    create_engine_from,
    create_session_factory,
)
from orchestrator.infrastructure.db import migrations as db_migrations

# the harness-table seed moved to `infrastructure/db/seed.py` for the reason the registry
# below moved: this module is at its 400-line cap and that is one subject of its own. Both
# names are re-exported here, where `run_migrations` names one collaborator and
# `tests/unit/test_main_harness_registry.py` reads the pin table from `orchestrator.main`.
from orchestrator.infrastructure.db.seed import (  # noqa: F401
    HARNESS_VERSION_SETTINGS,
    seed_harness_table,
)
from orchestrator.infrastructure.dbos import (
    build_engine,
    dependency_startup_sweep,
    launch_engine,
    schedule_engine_jobs,
    schedule_jobs,
    serving,
)
from orchestrator.infrastructure.git import SubprocessGit

# the registry moved to `infrastructure/harness/registry.py`, beside the adapter it names,
# because `infrastructure/dbos/startup.py` builds the walker's ports and may not import
# this module (AD-2). It is re-exported here because `tests/unit/test_main_harness_registry.py`
# imports it from `orchestrator.main`.
from orchestrator.infrastructure.harness import build_harnesses  # noqa: F401
from orchestrator.infrastructure.logging import configure_logging
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.templates_loader import load_shipped_templates

log = structlog.get_logger(__name__)

API_PREFIX = "/api/v1"
HTTP_UNAUTHORIZED = 401

PACKAGE = "orchestrator"

#: What FastAPI accepts as `lifespan`: a callable taking the app and yielding once.
Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]

#: How a request reaches a database session, and how it reaches the instance key.
SessionFactory = Callable[[], Session]
CryptoFactory = Callable[[], Crypto]


def package_version() -> str:
    """The distribution version, or a marker when running from an uninstalled source tree."""
    try:
        return version(PACKAGE)
    except PackageNotFoundError:  # pragma: no cover — an installed package is the norm
        return "0.0.0+source"


class Health(BaseModel):
    """The `/healthz` payload. Typed so the generated contract carries a real schema (AD-3)."""

    status: str
    version: str


def seed_shipped_templates(settings: Settings) -> list[SeedResult]:
    """Read `TEMPLATES_DIR` and seed it (SPEC CAP-3).

    Builds its own engine rather than sharing the one `main()` builds for serving requests,
    for the same reason `run_migrations` builds its own `session_factory`: the call site
    inside `migrating_lifespan` takes exactly one argument, `settings`. That engine is this
    function's alone, so it is this function's job to `dispose()` it — in a `finally`, so a
    seed that raises (`ShippedTemplateInvalid`) still releases the pool before the process
    exits on that failure.
    """
    files = load_shipped_templates(settings.templates_dir)
    if not files:
        # the four shipped files are the whole point of this story; a `TEMPLATES_DIR` that
        # resolves to none of them is almost certainly a misconfigured mount or a broken
        # image, not an instance meaning to run with zero Templates
        log.warning("no shipped templates found", templates_dir=str(settings.templates_dir))
    engine = create_engine_from(settings)
    try:
        session_factory = create_session_factory(engine)
        with SQLAlchemyUnitOfWork(session_factory) as uow:
            ports = TemplatePorts(
                uow=uow,
                templates=SQLAlchemyTemplateVersionRepository(uow.session),
                clock=SystemClock(),
            )
            results = seed_shipped(ports, files)
    finally:
        engine.dispose()
    for result in results:
        if result.inserted_as is not None:
            log.info(
                f"shipped template {result.name} seeded as v{result.inserted_as}",
                name=result.name,
                version=result.inserted_as,
            )
    return results


def run_migrations(settings: Settings) -> str:
    """The pre-serve start-up step: schema to head, the shipped Templates and the harness
    table seeded.

    Combined under this one name for the reason the module docstring gives: every test that
    replaces `main.run_migrations` takes exactly one argument, `settings`. The durable
    engine's launch is the fourth step for the same reason and one of its own (AD-6, FR-12):
    recovery of the Runs an earlier container was walking begins at that call, and it must
    not begin against a schema that has not been migrated.
    """
    head = db_migrations.run_migrations(settings)
    seed_shipped_templates(settings)
    seed_harness_table(settings)
    # last, and inside this function: see `infrastructure/dbos/startup.py`. A process that
    # is not serving — every unit test — has no engine registered and launches nothing.
    launch_engine()
    # after the launch: `engine.schedule` writes to the database the launch just opened
    # (SPEC CAP-11), the same reason `register_queue` runs after `start` inside it.
    schedule_jobs(settings)
    # the jobs that signal a Run rather than sweep one, and so need the engine itself
    # (SPEC CAP-7, FR-21) — `infrastructure/terminal_jobs.py` says why they register apart
    schedule_engine_jobs(settings)
    # re-enqueue or park any dependency-waiting Runs left unresolved by a crash (story 5-4)
    dependency_startup_sweep(settings)
    return head


def migrating_lifespan(settings: Settings) -> Lifespan:
    """The start-up step that migrates, seeds and launches before the socket is bound.

    Built here rather than inside `create_app` so that the only application that migrates
    is the one this module hands to uvicorn. See `infrastructure/db/migrations.py`.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # off the event loop, and not as an optimisation: the whole start-up step is
        # blocking I/O — alembic, the two seeds, and the durable engine's own launch — and
        # the engine refuses to register its queue from a thread that is running a loop,
        # because that registration writes to the database. uvicorn still waits for all of
        # it before it binds, which is the guarantee this lifespan exists to give.
        await asyncio.to_thread(run_migrations, settings)
        yield

    return lifespan


def crypto_factory(settings: Settings) -> CryptoFactory:
    """A `Crypto` that is built on first use, and then once.

    Constructing it here would refuse the `.env.example` placeholder at start-up, which is
    the value `main()` is called with in two unit tests. The adapter still validates its
    key strictly; the refusal simply moves from import time to the first request that needs
    a Project port — any of the four, read or write — where it becomes a 500.
    """

    @cache
    def build() -> Crypto:
        return FernetCrypto(settings.orchestrator_secret_key.get_secret_value())

    return build


def create_app(  # noqa: PLR0913 — one keyword per optional adapter, `git`'s own precedent
    settings: Settings,
    *,
    lifespan: Lifespan | None = None,
    session_factory: SessionFactory | None = None,
    crypto: CryptoFactory | None = None,
    git: Git | None = None,
    engine: WorkflowEngine | None = None,
) -> FastAPI:
    """Build the ASGI application. Adapters are constructed here and nowhere else.

    Without a `lifespan` the application performs no I/O at any point in its life — the
    shape every unit test builds. The ports are optional for the same reason: the contract
    exporter builds this application from `Settings.model_construct()` and only reads its
    routes, and a unit test overrides them through `dependency_overrides`.
    """
    app = FastAPI(
        title="ai-orchestrator backend-api",
        version=package_version(),
        lifespan=lifespan,
    )
    # the settings object dependencies read; nothing else re-reads the environment (AD-20)
    app.state.settings = settings
    # the adapters `api/providers.py` builds each request's ports from
    app.state.session_factory = session_factory
    app.state.crypto = crypto
    app.state.git = git
    app.state.engine = engine
    install_error_handlers(app)

    @app.get("/healthz", tags=["health"], response_model=Health)
    def healthz() -> Health:
        return Health(status="ok", version=package_version())

    # one dependency for the whole versioned surface: a feature router added later
    # inherits the bearer check — and its declared 401 — instead of having to remember them
    for router in (ping.router, projects.router, repositories.router, clone_check.router):
        _mount(app, router)
    _mount(app, repository_init.router)
    # before `templates.router`, and that is load-bearing: Starlette matches in registration
    # order and `templates.router` registers `GET /templates/{name}/{version}` last, so a
    # three-segment `GET /templates/{name}/graph` mounted after it would be swallowed as
    # `version="graph"` and answered 422 instead of reaching this operation at all.
    # `test_graph_text_router.py` reads this pair's own literal source, so unlike every
    # other router above and below, neither goes through the `_mount` helper.
    app.include_router(
        graph_text.router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_bearer)],
        responses={HTTP_UNAUTHORIZED: UNAUTHORIZED_RESPONSE},
    )
    app.include_router(
        templates.router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_bearer)],
        responses={HTTP_UNAUTHORIZED: UNAUTHORIZED_RESPONSE},
    )
    for router in (graph.router, runs.router):
        _mount(app, router)
    # after `runs.router`, and that is load-bearing the same way `graph_text.router` before
    # `templates.router` is: `GET /runs/{run_id}` and `GET /runs/preflight` are the same
    # shape to Starlette, which matches registration order, so the literal path has to be
    # checked first (`api/routers/run.py`'s own docstring; `test_run_router.py` pins it)
    for router in (
        run.router,
        run_detail.router,
        run_activity.router,
        run_attempts.router,
        step_detail.router,
        signals.router,
        run_files.router,
        harnesses.router,
        queue.router,
        history.router,
        trajectories.router,
    ):
        _mount(app, router)
    _mount(app, harness_readiness.router)
<<<<<<< HEAD
    _mount(app, harness_probe.router)
    _mount(app, start_run.router)
=======
>>>>>>> 61dba33 (wip: story 5-3 attempt 2 — review blocked (intent gap))

    return app


def _mount(app: FastAPI, router: APIRouter) -> None:
    """One feature router, on the versioned prefix, behind the one bearer dependency (AD-4)."""
    app.include_router(
        router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_bearer)],
        responses={HTTP_UNAUTHORIZED: UNAUTHORIZED_RESPONSE},
    )


def main() -> None:
    try:
        settings = Settings()
    except ValidationError as error:
        raise SystemExit(f"configuration error (AD-20): .env is incomplete\n{error}") from error

    configure_logging(settings.log_level)
    if not settings.gateway_enabled:
        log.warning("gateway disabled", spend="provisional")
    if not settings.tracing_enabled:
        log.warning("tracing disabled", traces="absent")
    # none of these opens a connection, so this stays inside the "no I/O before start-up" rule
    session_factory = create_session_factory(create_engine_from(settings))
    # the one place the git adapter is named. It holds GITHUB_TOKEN for the subprocess
    # environments it builds itself, and puts it nowhere else (AD-5)
    git = SubprocessGit(settings.github_token.get_secret_value())
    engine = build_engine(settings, session_factory, git)
    with serving(engine, session_factory, git):
        _serve(settings, session_factory, git, engine)


def _serve(
    settings: Settings,
    session_factory: SessionFactory,
    git: Git,
    engine: WorkflowEngine,
) -> None:
    """Hand uvicorn the application whose start-up step migrates, seeds and launches."""
    uvicorn.run(
        # the migration is the application's start-up step: uvicorn awaits it before it
        # binds, so the process never serves a half-migrated schema
        create_app(
            settings,
            lifespan=migrating_lifespan(settings),
            session_factory=session_factory,
            crypto=crypto_factory(settings),
            git=git,
            # the durable engine (AD-6): `POST /runs` enqueues through it, and the walker it
            # registered is what executes the Run
            engine=engine,
        ),
        # binds every interface: reached from the compose network, not from the host
        host="0.0.0.0",
        port=settings.backend_api_port,
        # uvicorn's default dictConfig would replace the JSON handler set just above,
        # leaving access and startup lines as plain text on the same stream
        log_config=None,
    )


if __name__ == "__main__":
    main()
