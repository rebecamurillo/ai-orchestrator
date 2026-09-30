"""`evaluate`: read one finished readiness Run back, and write what it proved (SPEC CAP-8).

Six lines, checked in the brief's own order, over the readiness Run's one story ("1",
`harness_readiness.READINESS_STORY_ID`) and the latest attempt of its build row: `story file
done`, `session id recorded`, `trace observed`, `spend attributable`, `verify exit 0`,
`run done`.

The rows are found by **kind**, never by step id (Operator decision 2026-09-30: the
orchestrator hardcodes no template name and no template step id; it follows the workflow and
triggers actions). "The build row" is the last `agent` row, in `seq` order, that ended `done`
— with several agent rows per story (plan, implement, review, …) the final one's `end_sha` is
where the story file's `status: done` is observable — falling back to the last agent row of
any status so the `build row is not done` text still applies. "The verify row" is the last
`shell` row in `seq` order. `Settings.readiness_template` names whichever Template the Run
was planned from; nothing here reads its step names, mirroring `record_trajectory`.

All six `ok` writes `enabled=True, failing_check=None`; otherwise `enabled=False` and
`failing_check` is the first failing line's own `"{check}: {text}"` — the exact form
`tests/e2e/test_harnesses.py`'s authorised assertion checks the values of.
`last_readiness_at`/`last_readiness_run_id` are written every time, pass or fail: a readiness
Run that could not even start still has to leave `GET /harnesses` telling the Operator so.

The fifth line is the one that reads two ways. The readiness fixture declares no
`quality_gate_command` (`harness_readiness_seed.py` says why), so its shell (verify) row is
planned away as `skipped · no quality_gate_command` and no gate ever runs. That is not a
failure, and the line is `ok` — but it is named `no quality gate to run`, not `verify exit
0`, because nothing exited 0. `enabled` therefore means "this harness works": it starts,
finishes, records a session, emits a trace, and its spend is attributable. It does not mean
"this harness can turn a red repository green" — that is the `gates-repo` fixture's job
(`tests/unit/test_gates_fixture_uj3.py`, `tests/e2e` UJ-3).

Called from the walker's own `on_terminal` hook (`infrastructure/dbos/walker.py`,
`infrastructure/db/harness_readiness.py`) for every terminal Run, not only `done` ones — a
Run that is not Project `readiness`, or whose harness is not stored, is a silent no-op,
mirroring `run_finished.on_finished`'s own template-name gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from orchestrator.application.steps import AGENT_KIND, SHELL_KIND
from orchestrator.application.templates.lists import _states_done
from orchestrator.application.templates.plan_model import names_a_field
from orchestrator.application.templates.rows import SKIPPED
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

#: What the fifth line is called instead when the Repository declared no quality gate, so
#: the planner skipped the frame's `verify` row before it could exit anything. The readiness
#: fixture is seeded exactly that way (`harness_readiness_seed.py`): readiness proves the
#: harness, not the repository. The line is `ok` — nothing failed — but it is deliberately
#: **not** called `verify exit 0`, because no gate exited 0 here; there was no gate. A check
#: that claimed a passing gate it never ran would tell the Operator something untrue about
#: what `enabled` means.
CHECK_NO_QUALITY_GATE = "no quality gate to run"


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
    build_row = _build_row(rows)
    verify_row = _last_of_kind(rows, SHELL_KIND)
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


def _build_row(rows: list[StepRun]) -> StepRun | None:
    """The last `agent` row that ended `done`, else the last `agent` row, else `None`.

    Selected by kind, not by step id (Operator decision 2026-09-30): the readiness Template
    may split a story over any number of agent rows under any names. The last `done` one is
    the attempt whose `end_sha` holds the story file as the story left it; when none is
    `done` the last agent row stands in so `_story_file_line` says so, rather than `None`
    reading as "no row at all".
    """
    agents = [row for row in rows if row.kind == AGENT_KIND]
    done = [row for row in agents if row.status == DONE]
    return _last(done) or _last(agents)


def _last_of_kind(rows: list[StepRun], kind: str) -> StepRun | None:
    """The last row of `kind` in `seq` order, or `None` when the plan has none."""
    return _last([row for row in rows if row.kind == kind])


def _last(rows: list[StepRun]) -> StepRun | None:
    return max(rows, key=lambda row: row.seq, default=None)


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
    # the attempt's own harness, because the rule differs per harness (AD-10, AD-11): a
    # `codex` attempt whose spans did not parent is still proven by the session-level
    # evidence AD-11's universal floor leaves (7.2). The line's wording does not change.
    #
    # ...and the attempt's own window, because `local`'s rule *is* one (7.3): the OpenCode
    # Langfuse plugin carries no attempt id, so the only thing separating this attempt's
    # generations from another attempt of the same Run is when they happened. Both halves are
    # keyword-only on the port; this is the one caller that holds the attempt they come from.
    observed = ports.tracer.attempt_observed(
        run_id,
        build_attempt.id,
        harness=build_attempt.harness,
        started_at=build_attempt.started_at,
        ended_at=build_attempt.ended_at,
    )
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
    """What the frame's shell (verify) row proved — or that there was nothing to prove.

    Three outcomes, not two. A `done` row ran the gate and it exited 0. A row the planner
    skipped because the Repository declares no command for it ran nothing, and says so
    under its own check name: the absence of a gate is not the pass of one. Anything
    else — failed, errored, or skipped for any other reason, including `skipped by
    operator` — is a readiness failure and keeps the `verify exit 0` wording, because that
    is the check the Operator was owed and did not get.

    Which command is missing is the row's to say, not this function's. `verify` ran
    `{{repository.quality_gate_command}}` when this was written and runs
    `{{repository.unit_test_command}}` now; both are "the Repository states no command for
    this row", so the test is `names_a_field` and the text is the row's own reason.
    """
    if verify_row is not None and verify_row.status == DONE:
        return EvaluationLine(check=CHECK_VERIFY_EXIT_0, ok=True, text="verify exited 0")
    if verify_row is not None and names_a_field(verify_row.reason or ""):
        return EvaluationLine(
            check=CHECK_NO_QUALITY_GATE,
            ok=True,
            text=f"{SKIPPED} · {verify_row.reason}",
        )
    return EvaluationLine(check=CHECK_VERIFY_EXIT_0, ok=False, text="verify did not pass")


def _run_done_line(run: Run) -> EvaluationLine:
    ok = run.status == DONE
    text = "run finished done" if ok else f"run finished {run.status}"
    return EvaluationLine(check=CHECK_RUN_DONE, ok=ok, text=text)
