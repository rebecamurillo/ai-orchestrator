"""The senior session turn's own workflow (AD-6, AD-23), declared beside the walk and never
inside it.

`run_session_turn(attempt_id)` is two durable steps with the engine's retries off:
`session_turn` dispatches the turn, `session_commit` commits, closes and bills it. The rules
are `application/use_cases/session_turn.py`'s; what is here is the durability. The commit
runs in a `finally`, so a turn whose own step raised is still closed: a turn left open would
refuse `session_end` for the rest of the session. A replay takes the same path, because the
first step's recorded outcome is what decides it.

Its step sequence is its own: adding it changes nothing the walker replays, which is why
`DBOS_APPLICATION_VERSION` stays where it is. Changing these two steps is what would bump it
(AD-6, as amended for AD-23).
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from orchestrator.application.use_cases.session_turn import TurnPorts, commit_turn, run_turn
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.infrastructure.dbos.facade import DurableEngine
from orchestrator.infrastructure.dbos.walker import WalkerDeps


def build_session_turn(engine: DurableEngine, deps: WalkerDeps) -> Callable[[str], None]:
    """Declare the turn's two steps and its workflow on `engine`, and return the workflow."""
    turn = engine.step(_session_turn(deps))
    commit = engine.step(_session_commit(deps))

    def run_session_turn(attempt_id: str) -> None:
        try:
            turn(attempt_id)
        finally:
            commit(attempt_id)

    return engine.workflow(run_session_turn)


def _ports(deps: WalkerDeps, writers: WriterPorts) -> TurnPorts:
    return TurnPorts(writers=writers, step=deps.step_ports, read_environment=deps.read_environment)


def _session_turn(deps: WalkerDeps) -> Callable[[str], None]:
    def session_turn(attempt_id: str) -> None:
        with deps.open_ports() as writers:
            run_turn(_ports(deps, writers), UUID(attempt_id))

    return session_turn


def _session_commit(deps: WalkerDeps) -> Callable[[str], None]:
    def session_commit(attempt_id: str) -> None:
        with deps.open_ports() as writers:
            commit_turn(_ports(deps, writers), UUID(attempt_id))

    return session_commit
