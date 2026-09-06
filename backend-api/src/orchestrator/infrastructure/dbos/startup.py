"""Building the durable engine, and launching it inside the application's start-up step.

**Why the launch is here and not beside `uvicorn.run`.** Operations puts it after the
migrations and the seeds and before the server binds, and `main.run_migrations` is the one
name that start-up step has: `tests/unit/test_migrations.py` proves "migrate before bind" by
replacing that function wholesale, so anything a unit test drives that sits *outside* it —
in `main()`, in the lifespan, anywhere — runs for real against a database that is not there
(AD-18). Putting the launch inside it makes the whole start-up step one replaceable name.

**Why it is guarded.** `tests/unit/test_main_templates_seed.py` calls the real
`main.run_migrations` with its three collaborators stubbed, so a fourth that opened a
connection would fail that test too. `serving` is the answer and it is not a trick: an
engine is launched only while a composition root is actually serving with one, which is
exactly the length of `uvicorn.run`. A process that never got that far — every unit test —
has nothing to launch, and says so by having nothing registered.

**Why the kind modules are imported here, and not by `application/steps/__init__.py`
itself.** Each `steps/<kind>.py` module's own `register(...)` call is what fills the
registry (AD-9), but `checkpoint.py` and `shell.py` need constants from
`application/templates/`, and those modules import `application/steps` right back for
`KIND_META` — importing them *from inside* the package would be the cycle that makes.
Importing them here instead works because this module is a full layer above `application/`
(AD-2): by the time anything reaches this import, `application.steps` has always already
finished, whichever module happened to need it first.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial

from orchestrator.application.steps import StepPorts
from orchestrator.application.steps import checkpoint as _checkpoint  # noqa: F401
from orchestrator.application.steps import plan_check as _plan_check  # noqa: F401
from orchestrator.application.steps import shell as _shell  # noqa: F401
from orchestrator.domain.ports.git import Git
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db.writers import SessionFactory, open_writer_ports
from orchestrator.infrastructure.dbos.adapter import DbosWorkflowEngine
from orchestrator.infrastructure.dbos.config import engine_config
from orchestrator.infrastructure.dbos.facade import RealEngine
from orchestrator.infrastructure.dbos.walker import WalkerDeps
from orchestrator.infrastructure.process import RealProcessRunner
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.workspace import FsWorkspace

#: The engine this process is serving with, for as long as it is serving. A list rather than
#: a rebound name so `serving` needs no `global`: what matters is that it is empty in any
#: process that is not serving, and that it empties itself again on the way out.
_SERVING: list[DbosWorkflowEngine] = []


def walker_deps(settings: Settings, session_factory: SessionFactory, git: Git) -> WalkerDeps:
    """What the walker's steps run on: a session per step, the executors' ports, the deadline.

    Its own function so the wiring is assertable. Every value here comes from the typed
    settings (AD-20), and `HUMAN_WAIT_SECONDS` reaches the walker's `recv` through this
    object and nowhere else. `workspace=FsWorkspace` passes the class itself, not an
    instance: `StepPorts.workspace` is a factory a row calls with its own `cwd`
    (`application/steps/context.py`'s own docstring says why one static `Workspace` cannot
    be right for every Run).
    """
    return WalkerDeps(
        open_ports=partial(open_writer_ports, session_factory),
        step_ports=StepPorts(
            git=git,
            clock=SystemClock(),
            work_dir=str(settings.work_dir),
            process=RealProcessRunner(),
            workspace=FsWorkspace,
        ),
        human_wait_seconds=settings.human_wait_seconds,
    )


def build_engine(
    settings: Settings, session_factory: SessionFactory, git: Git
) -> DbosWorkflowEngine:
    """The durable `WorkflowEngine`, wired to the walker's ports. Opens no connection."""
    return DbosWorkflowEngine(
        engine_config(settings),
        RealEngine(),
        walker_deps(settings, session_factory, git),
    )


@contextmanager
def serving(engine: DbosWorkflowEngine) -> Iterator[DbosWorkflowEngine]:
    """Name the engine the start-up step is to launch, for the length of the server's life."""
    _SERVING.append(engine)
    try:
        yield engine
    finally:
        # remove, not clear: a second block would otherwise unregister an engine it never
        # named. Nothing nests one today; this costs nothing and does not have to be read
        # twice to be sure of that.
        _SERVING.remove(engine)


def launch_engine() -> None:
    """Launch the engine this process is serving with, if it is serving with one."""
    for engine in _SERVING:
        engine.launch()
