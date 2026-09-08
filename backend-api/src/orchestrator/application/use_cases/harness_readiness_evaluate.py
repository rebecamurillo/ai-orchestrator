"""`evaluate`: read one finished readiness Run back, and write what it proved (SPEC CAP-8).

Six lines, checked in the brief's own order, over the readiness Run's one story ("1",
`harness_readiness.READINESS_STORY_ID`) and its `build` row's latest attempt: `story file
done`, `session id recorded`, `trace observed`, `spend attributable`, `verify exit 0`,
`run done`. All six `ok` writes `enabled=True, failing_check=None`; otherwise `enabled=False`
and `failing_check` is the first failing line's own `"{check}: {text}"` — the exact form
`tests/e2e/test_harnesses.py`'s authorised assertion checks the values of.
`last_readiness_at`/`last_readiness_run_id` are written every time, pass or fail: a readiness
Run that could not even start still has to leave `GET /harnesses` telling the Operator so.

Called from the walker's own `on_terminal` hook (`infrastructure/dbos/walker.py`,
`infrastructure/db/harness_readiness.py`) for every terminal Run, not only `done` ones — a
Run that is not Project `readiness`, or whose harness is not stored, is a silent no-op,
mirroring `run_finished.on_finished`'s own template-name gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from orchestrator.application.templates.lists import _states_done
from orchestrator.application.use_cases.clone_check import _base
from orchestrator.application.use_cases.harness_readiness import (
    READINESS_SPEC_FOLDER,
    READINESS_STORY_ID,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.harness import EvaluationLine, Harness
from orchestrator.domain.entities.project import READINESS_PROJECT_SLUG
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.gateway import Gateway
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.harnesses import HarnessRepository
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    ProjectRepository,
    RepositoryRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.tracer import Tracer
from orchestrator.domain.ports.unit_of_work import UnitOfWork

#: The one `StepStatus`/`RunStatus` value every line below checks for (`domain/statuses.py`
#: declares no constant for it, only the `Literal` the two alphabets share).
DONE = "done"

CHECK_STORY_FILE_DONE = "story file done"
CHECK_SESSION_ID = "session id recorded"
CHECK_TRACE_OBSERVED = "trace observed"
CHECK_SPEND_ATTRIBUTABLE = "spend attributable"
CHECK_VERIFY_EXIT_0 = "verify exit 0"
CHECK_RUN_DONE = "run done"


@dataclass(frozen=True)
class HarnessEvaluatePorts:
    """Everything `evaluate` reaches the outside world through."""

    runs: RunRepository
    steps: StepRunRepository
    attempts: AttemptRepository
    harnesses: HarnessRepository
    projects: ProjectRepository
    repositories: RepositoryRepository
    uow: UnitOfWork
    clock: Clock
    work_dir: Path
    #: `None` degrades every line it feeds to a stated failure rather than raising — the
    #: same tolerance `StepPorts.tracer`/`spend_writes` already give a process wired without
    #: one (5.2/5.7's own precedent).
    git: Git | None = None
    tracer: Tracer | None = None
    gateway: Gateway | None = None


def evaluate(ports: HarnessEvaluatePorts, run_id: UUID) -> Harness | None:
    """Write `enabled`/`failing_check`/`last_readiness_at`/`last_readiness_run_id`/`lines`
    onto the Run's own harness, or `None` when there is nothing here to evaluate."""
    run = ports.runs.get(run_id)
    if run is None:
        return None
    project = ports.projects.get(run.project_id)
    if project is None or project.slug != READINESS_PROJECT_SLUG:
        return None
    name = run.inputs.get("harness")
    harness = ports.harnesses.get(name) if isinstance(name, str) else None
    if harness is None:
        return None

    lines = _lines(ports, run, project.slug)
    failing = next((line for line in lines if not line.ok), None)
    updated = harness.model_copy(
        update={
            "enabled": failing is None,
            "failing_check": None if failing is None else f"{failing.check}: {failing.text}",
            "last_readiness_at": ports.clock.now(),
            "last_readiness_run_id": run_id,
            "lines": tuple(lines),
        }
    )
    ports.harnesses.update(updated)
    ports.uow.commit()
    return updated


def _lines(ports: HarnessEvaluatePorts, run: Run, project_slug: str) -> list[EvaluationLine]:
    rows = ports.steps.list_for_run(run.id)
    build_row = _row(rows, ".build")
    verify_row = _row(rows, ".verify")
    build_attempt = ports.attempts.get_latest(build_row.id) if build_row is not None else None
    repository = ports.repositories.get(run.repository_id)
    return [
        _story_file_line(ports, project_slug, repository, build_row, build_attempt),
        _session_id_line(build_attempt),
        _trace_line(ports, run.id, build_attempt),
        _spend_line(ports, run.id, build_attempt),
        _verify_line(verify_row),
        _run_done_line(run),
    ]


def _row(rows: list[StepRun], suffix: str) -> StepRun | None:
    return next((row for row in rows if row.path.endswith(suffix)), None)


def _story_file_line(
    ports: HarnessEvaluatePorts,
    project_slug: str,
    repository: Repository | None,
    build_row: StepRun | None,
    build_attempt: Attempt | None,
) -> EvaluationLine:
    if build_row is None or build_row.status != DONE:
        return EvaluationLine(check=CHECK_STORY_FILE_DONE, ok=False, text="build row is not done")
    if repository is None:
        return EvaluationLine(check=CHECK_STORY_FILE_DONE, ok=False, text="no repository stored")
    if build_attempt is None or build_attempt.end_sha is None:
        return EvaluationLine(
            check=CHECK_STORY_FILE_DONE, ok=False, text="no build attempt end sha recorded"
        )
    if ports.git is None:
        return EvaluationLine(check=CHECK_STORY_FILE_DONE, ok=False, text="no git adapter wired")
    base = _base(ports.work_dir, project_slug, repository.slug)
    prefix = f"{READINESS_SPEC_FOLDER}/stories"
    opening = f"{prefix}/{READINESS_STORY_ID}-"
    matches = [
        path
        for path in ports.git.list_files(base, build_attempt.end_sha, prefix)
        if path.startswith(opening) and path.endswith(".md")
    ]
    if not matches:
        return EvaluationLine(
            check=CHECK_STORY_FILE_DONE, ok=False, text=f"no story file at {build_attempt.end_sha}"
        )
    text = ports.git.read_file(base, build_attempt.end_sha, matches[0])
    ok = text is not None and _states_done(text)
    detail = "status: done" if ok else f"story file is not status: done at {build_attempt.end_sha}"
    return EvaluationLine(check=CHECK_STORY_FILE_DONE, ok=ok, text=detail)


def _session_id_line(build_attempt: Attempt | None) -> EvaluationLine:
    if build_attempt is not None and build_attempt.session_id:
        return EvaluationLine(
            check=CHECK_SESSION_ID, ok=True, text=f"session {build_attempt.session_id}"
        )
    return EvaluationLine(check=CHECK_SESSION_ID, ok=False, text="no session id recorded")


def _trace_line(
    ports: HarnessEvaluatePorts, run_id: UUID, build_attempt: Attempt | None
) -> EvaluationLine:
    if build_attempt is None:
        return EvaluationLine(check=CHECK_TRACE_OBSERVED, ok=False, text="no attempt recorded")
    if ports.tracer is None:
        return EvaluationLine(check=CHECK_TRACE_OBSERVED, ok=False, text="no tracer wired")
    observed = ports.tracer.attempt_observed(run_id, build_attempt.id)
    text = (
        f"spans observed for attempt {build_attempt.id}"
        if observed
        else f"no spans for attempt {build_attempt.id}"
    )
    return EvaluationLine(check=CHECK_TRACE_OBSERVED, ok=observed, text=text)


def _spend_line(
    ports: HarnessEvaluatePorts, run_id: UUID, build_attempt: Attempt | None
) -> EvaluationLine:
    if build_attempt is None:
        return EvaluationLine(check=CHECK_SPEND_ATTRIBUTABLE, ok=False, text="no attempt recorded")
    if ports.gateway is None:
        return EvaluationLine(check=CHECK_SPEND_ATTRIBUTABLE, ok=False, text="no gateway wired")
    spend = ports.gateway.spend_for_attempt(run_id, build_attempt.id)
    ok = not spend.provisional and spend.calls > 0
    text = f"{spend.calls} calls attributed" if ok else "spend is provisional or has no calls"
    return EvaluationLine(check=CHECK_SPEND_ATTRIBUTABLE, ok=ok, text=text)


def _verify_line(verify_row: StepRun | None) -> EvaluationLine:
    ok = verify_row is not None and verify_row.status == DONE
    text = "verify exited 0" if ok else "verify did not pass"
    return EvaluationLine(check=CHECK_VERIFY_EXIT_0, ok=ok, text=text)


def _run_done_line(run: Run) -> EvaluationLine:
    ok = run.status == DONE
    text = "run finished done" if ok else f"run finished {run.status}"
    return EvaluationLine(check=CHECK_RUN_DONE, ok=ok, text=text)
