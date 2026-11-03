"""A parked Run wired for the Operator senior session (story 2-3, AD-23).

`writer_fixtures.World` plus what `handle_signal` reaches beyond `signal_run`: a `FakeGit`
the anchor check diffs through, and a harness registry on `SignalPorts.preflight` the start
check probes. Every double is a shared fake (AD-18).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.signal_run import SignalPorts
from orchestrator.application.use_cases.signals import SignalEffectPorts, handle_signal
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.harness import HarnessCapabilities, ProbeResult
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

BUILD = "stories[0].build"
WORKTREE = "/work/demo/app/wt/epics-1"
SPEC_FOLDER = "specs/demo"
MODEL = "claude-sonnet"
START_SHA = "a" * 40
HEAD_SHA = "b" * 40

PROBE_OK = ProbeResult(ok=True, failing_reason=None, version="1.0.0", models=[MODEL])


def probing(*results: ProbeResult, resume: bool = True, name: str = "claude") -> FakeHarness:
    return FakeHarness(
        name=name,
        capabilities=HarnessCapabilities(resume=resume),
        probe_results=list(results) or [PROBE_OK] * 4,
    )


@dataclass
class SessionWorld:
    world: World
    git: FakeGit
    harnesses: dict[str, FakeHarness]

    @property
    def ports(self) -> SignalEffectPorts:
        preflight = PreflightPorts(
            git=self.git,
            templates=FakeTemplateVersionRepository(),
            runs=self.world.ports.runs,
            harnesses=FakeHarnessRepository(),
            repositories=FakeRepositoryRepository(),
            projects=FakeProjectRepository(),
            bmad_version="6.0.0",
            max_active_runs=2,
            work_dir=Path("/work"),
            harness_registry=dict(self.harnesses),
        )
        return SignalEffectPorts(
            signal=SignalPorts(
                writers=self.world.ports, engine=self.world.engine, preflight=preflight
            ),
            git=self.git,
            process=FakeProcessRunner(),
            work_dir="/work",
            read_environment=lambda _run_id: None,
        )

    def send(self, kind: str, **payload: Any) -> Any:
        signal = Signal(kind=kind, payload=dict(payload))  # type: ignore[arg-type]
        return handle_signal(self.ports, self.world.run.id, signal)

    def start(self, scope: str = "story", harness: str = "claude", model: str = MODEL) -> Any:
        return self.send("session_start", scope=scope, harness=harness, model=model)

    def turn(self, n: int = 1, **over: Any) -> Attempt:
        """One `session` attempt on the parked row, started now (after the last start)."""
        row = self.world.row(self.world.stored_run().park_path or BUILD)
        fields: dict[str, Any] = {
            "id": new_id(),
            "run_id": self.world.run.id,
            "step_run_id": row.id,
            "n": n,
            "status": "done",
            "role": "session",
            "started_at": self.world.clock.now(),
            "ended_at": self.world.clock.now(),
            "start_sha": START_SHA,
        }
        fields.update(over)
        attempt = Attempt(**fields)
        self.world.ports.attempts.add(attempt)
        return attempt


def a_session_world(  # noqa: PLR0913 — one keyword per stop fact, each optional
    *,
    park_kind: str = "blocked",
    park_path: str | None = BUILD,
    row_status: str = "blocked",
    plan: tuple[tuple[str, str], ...] = EPIC_PLAN,
    git: FakeGit | None = None,
    harnesses: dict[str, FakeHarness] | None = None,
    with_resolved: dict[str, dict[str, Any]] | None = None,
    **over: Any,
) -> SessionWorld:
    fields: dict[str, Any] = {
        "park_kind": park_kind,
        "park_path": park_path,
        "park_reason": "intent gap",
        "worktree_path": WORKTREE,
        "inputs": {"spec_folder": SPEC_FOLDER},
    }
    fields.update(over)
    statuses = {park_path: row_status} if park_path is not None else {}
    world = a_world("needs_you", plan, statuses, with_resolved, **fields)  # type: ignore[arg-type]
    return SessionWorld(
        world=world,
        git=git or FakeGit(),
        harnesses=harnesses if harnesses is not None else {"claude": probing()},
    )
