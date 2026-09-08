"""`harness_readiness_evaluate.evaluate` (SPEC CAP-8): read one Run back, write a harness.

Each of the six lines is proven twice: once through its own private function, for every
branch that function can take, and once through `evaluate` itself, for the acceptance
criteria's own shape — all six `ok` enables the harness, and each line failing alone is
`failing_check`'s exact `"{check}: {text}"`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from orchestrator.application.use_cases.harness_readiness_evaluate import (
    CHECK_RUN_DONE,
    CHECK_SESSION_ID,
    CHECK_SPEND_ATTRIBUTABLE,
    CHECK_STORY_FILE_DONE,
    CHECK_TRACE_OBSERVED,
    CHECK_VERIFY_EXIT_0,
    HarnessEvaluatePorts,
    _run_done_line,
    _session_id_line,
    _spend_line,
    _story_file_line,
    _trace_line,
    _verify_line,
    evaluate,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.harness import Harness
from orchestrator.domain.entities.project import READINESS_PROJECT_SLUG, Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.gateway import AttemptSpend
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository
from tests.unit.fakes.tracer import FakeTracer

NOW = datetime(2026, 3, 4, tzinfo=UTC)
WORK_DIR = Path("/work")
SPEC_FOLDER = "specs/readiness"
END_SHA = "e" * 40
DONE_STORY = "---\nstatus: done\n---\n\nbody\n"
OPEN_STORY = "---\nstatus: in-progress\n---\n\nbody\n"


def a_project(*, slug: str = READINESS_PROJECT_SLUG) -> Project:
    return Project(
        id=new_id(),
        slug=slug,
        name="Readiness",
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        builtin=slug == READINESS_PROJECT_SLUG,
        created_at=NOW,
        updated_at=NOW,
    )


def a_repository(project_id: UUID, *, slug: str = "readiness-repo") -> Repository:
    return Repository(
        id=new_id(),
        project_id=project_id,
        slug=slug,
        url="file:///work/readiness/origin.git",
        default_branch="main",
        install_command="",
        quality_gate_command="sh check.sh",
        unit_test_command="",
        test_globs=(),
        package_manager="other",
        clone_check=CloneCheck.pending(),
        created_at=NOW,
        updated_at=NOW,
    )


def a_run(*, project_id: UUID, repository_id: UUID, status: str = "done") -> Run:
    return Run(
        id=new_id(),
        project_id=project_id,
        repository_id=repository_id,
        template_name="epic",
        template_version=1,
        inputs={"harness": "claude", "branch": "readiness/claude/2026-03-04"},
        status=status,  # type: ignore[arg-type]
        budget_usd=Decimal("5"),
        created_at=NOW,
    )


def a_row(run_id: UUID, *, path: str, seq: int = 1, status: str = "done") -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run_id,
        seq=seq,
        path=path,
        label=path,
        kind="agent",
        gate="liveness",  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
    )


def an_attempt(
    run_id: UUID,
    step_run_id: UUID,
    *,
    session_id: str | None = "sess-1",
    end_sha: str | None = END_SHA,
) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=run_id,
        step_run_id=step_run_id,
        n=1,
        status="done",  # type: ignore[arg-type]
        session_id=session_id,
        end_sha=end_sha,
    )


class World:
    """A Run of Project `readiness`, its build/verify rows, and a stored harness — every
    port `evaluate` reads, all fully wired and passing by default."""

    def __init__(self) -> None:
        self.project = a_project()
        self.repository = a_repository(self.project.id)
        self.run = a_run(project_id=self.project.id, repository_id=self.repository.id)
        self.build_row = a_row(self.run.id, path="stories.1.story.build", seq=1)
        self.verify_row = a_row(self.run.id, path="stories.1.story.verify", seq=2)
        self.attempt = an_attempt(self.run.id, self.build_row.id)
        self.harness = Harness(name="claude", version_pin="2.1.258")

        self.runs = FakeRunRepository([self.run])
        self.steps = FakeStepRunRepository([self.build_row, self.verify_row])
        self.attempts = FakeAttemptRepository([self.attempt])
        self.harnesses = FakeHarnessRepository([self.harness])
        self.projects = FakeProjectRepository([self.project])
        self.repositories = FakeRepositoryRepository([self.repository])
        self.uow = FakeUnitOfWork()
        self.clock = FakeClock(NOW)
        self.tracer = FakeTracer()
        self.tracer.observed[(self.run.id, self.attempt.id)] = True
        self.gateway = FakeGateway()
        self.gateway.script(
            self.run.id,
            self.attempt.id,
            AttemptSpend(
                usd=Decimal("1"), tokens_in=1, tokens_out=1, by_model=(), calls=3, provisional=False
            ),
        )
        self.git = FakeGit(
            files={(END_SHA, f"{SPEC_FOLDER}/stories/1-create-hello.md"): DONE_STORY},
            listings={
                (END_SHA, f"{SPEC_FOLDER}/stories"): [f"{SPEC_FOLDER}/stories/1-create-hello.md"]
            },
        )

    def ports(self, **overrides: object) -> HarnessEvaluatePorts:
        base = dict(
            runs=self.runs,
            steps=self.steps,
            attempts=self.attempts,
            harnesses=self.harnesses,
            projects=self.projects,
            repositories=self.repositories,
            uow=self.uow,
            clock=self.clock,
            work_dir=WORK_DIR,
            git=self.git,
            tracer=self.tracer,
            gateway=self.gateway,
        )
        base.update(overrides)
        return HarnessEvaluatePorts(**base)  # type: ignore[arg-type]

    def evaluate(self, **overrides: object) -> Harness | None:
        with self.uow:
            return evaluate(self.ports(**overrides), self.run.id)


# ── `evaluate` itself ────────────────────────────────────────────────────────────────────


def test_all_six_lines_ok_enables_the_harness() -> None:
    world = World()

    updated = world.evaluate()

    assert updated is not None
    assert updated.enabled is True
    assert updated.failing_check is None
    assert updated.last_readiness_at == NOW
    assert updated.last_readiness_run_id == world.run.id
    assert [line.check for line in updated.lines] == [
        CHECK_STORY_FILE_DONE,
        CHECK_SESSION_ID,
        CHECK_TRACE_OBSERVED,
        CHECK_SPEND_ATTRIBUTABLE,
        CHECK_VERIFY_EXIT_0,
        CHECK_RUN_DONE,
    ]
    assert all(line.ok for line in updated.lines)
    assert world.uow.committed is True


def test_trace_not_observed_disables_with_the_acs_own_exact_wording() -> None:
    world = World()
    world.tracer.observed.clear()

    updated = world.evaluate()

    assert updated is not None
    assert updated.enabled is False
    assert updated.failing_check == f"trace observed: no spans for attempt {world.attempt.id}"


def test_session_id_missing_is_the_first_and_only_failing_line() -> None:
    world = World()
    world.attempts.attempts[world.attempt.id] = world.attempt.model_copy(
        update={"session_id": None}
    )

    updated = world.evaluate()

    assert updated is not None
    assert updated.failing_check == "session id recorded: no session id recorded"


def test_spend_provisional_disables() -> None:
    world = World()
    world.gateway.script(
        world.run.id,
        world.attempt.id,
        AttemptSpend(
            usd=Decimal("0"), tokens_in=0, tokens_out=0, by_model=(), calls=0, provisional=True
        ),
    )

    updated = world.evaluate()

    assert updated is not None
    assert updated.failing_check == "spend attributable: spend is provisional or has no calls"


def test_verify_not_done_disables() -> None:
    world = World()
    world.steps.steps[world.verify_row.id] = world.verify_row.model_copy(
        update={"status": "skipped"}
    )

    updated = world.evaluate()

    assert updated is not None
    assert updated.failing_check == "verify exit 0: verify did not pass"


def test_run_not_done_disables() -> None:
    world = World()
    world.runs.runs[world.run.id] = world.run.model_copy(update={"status": "failed"})

    updated = world.evaluate()

    assert updated is not None
    assert updated.failing_check == "run done: run finished failed"
    # written even though the run never reached done (brief: "always")
    assert updated.last_readiness_run_id == world.run.id


def test_story_file_not_done_disables() -> None:
    world = World()
    world.git.files[(END_SHA, f"{SPEC_FOLDER}/stories/1-create-hello.md")] = OPEN_STORY

    updated = world.evaluate()

    assert updated is not None
    assert updated.failing_check == (
        f"story file done: story file is not status: done at {END_SHA}"
    )


def test_answers_none_when_the_run_does_not_exist() -> None:
    world = World()

    with world.uow:
        assert evaluate(world.ports(), new_id()) is None


def test_answers_none_when_the_run_is_not_project_readiness() -> None:
    world = World()
    other_project = a_project(slug="not-readiness")
    world.projects.add(other_project)
    world.runs.runs[world.run.id] = world.run.model_copy(update={"project_id": other_project.id})

    assert world.evaluate() is None


def test_answers_none_when_the_project_is_gone() -> None:
    world = World()
    world.projects.projects.clear()

    assert world.evaluate() is None


def test_answers_none_when_the_run_names_no_harness() -> None:
    world = World()
    world.runs.runs[world.run.id] = world.run.model_copy(update={"inputs": {}})

    assert world.evaluate() is None


def test_answers_none_when_the_named_harness_is_not_stored() -> None:
    world = World()
    world.harnesses.harnesses.clear()

    assert world.evaluate() is None


# ── `_story_file_line` ───────────────────────────────────────────────────────────────────


def test_story_file_line_fails_when_the_build_row_is_not_done() -> None:
    world = World()
    row = world.build_row.model_copy(update={"status": "error"})

    line = _story_file_line(world.ports(), world.project.slug, world.repository, row, world.attempt)

    assert line.ok is False
    assert line.text == "build row is not done"


def test_story_file_line_fails_when_the_build_row_is_missing() -> None:
    world = World()

    line = _story_file_line(world.ports(), world.project.slug, world.repository, None, None)

    assert line.ok is False
    assert line.text == "build row is not done"


def test_story_file_line_fails_when_the_repository_is_gone() -> None:
    world = World()

    line = _story_file_line(world.ports(), world.project.slug, None, world.build_row, world.attempt)

    assert line.ok is False
    assert line.text == "no repository stored"


def test_story_file_line_fails_when_there_is_no_attempt() -> None:
    world = World()

    line = _story_file_line(
        world.ports(), world.project.slug, world.repository, world.build_row, None
    )

    assert line.ok is False
    assert line.text == "no build attempt end sha recorded"


def test_story_file_line_fails_when_the_attempt_has_no_end_sha() -> None:
    world = World()
    attempt = world.attempt.model_copy(update={"end_sha": None})

    line = _story_file_line(
        world.ports(), world.project.slug, world.repository, world.build_row, attempt
    )

    assert line.ok is False
    assert line.text == "no build attempt end sha recorded"


def test_story_file_line_fails_when_no_git_adapter_is_wired() -> None:
    world = World()

    line = _story_file_line(
        world.ports(git=None), world.project.slug, world.repository, world.build_row, world.attempt
    )

    assert line.ok is False
    assert line.text == "no git adapter wired"


def test_story_file_line_fails_when_no_story_file_matches() -> None:
    world = World()
    world.git.listings.clear()
    world.git.files.clear()

    line = _story_file_line(
        world.ports(), world.project.slug, world.repository, world.build_row, world.attempt
    )

    assert line.ok is False
    assert line.text == f"no story file at {END_SHA}"


def test_story_file_line_passes_when_the_story_file_states_done() -> None:
    world = World()

    line = _story_file_line(
        world.ports(), world.project.slug, world.repository, world.build_row, world.attempt
    )

    assert line.ok is True
    assert line.text == "status: done"


# ── `_session_id_line` ───────────────────────────────────────────────────────────────────


def test_session_id_line_passes_with_a_recorded_session() -> None:
    world = World()

    line = _session_id_line(world.attempt)

    assert line.ok is True
    assert line.text == f"session {world.attempt.session_id}"


def test_session_id_line_fails_with_no_attempt() -> None:
    assert _session_id_line(None).ok is False


def test_session_id_line_fails_with_an_empty_session_id() -> None:
    world = World()
    attempt = world.attempt.model_copy(update={"session_id": ""})

    assert _session_id_line(attempt).ok is False


# ── `_trace_line` ────────────────────────────────────────────────────────────────────────


def test_trace_line_fails_with_no_attempt() -> None:
    world = World()

    line = _trace_line(world.ports(), world.run.id, None)

    assert line.ok is False
    assert line.text == "no attempt recorded"


def test_trace_line_fails_with_no_tracer_wired() -> None:
    world = World()

    line = _trace_line(world.ports(tracer=None), world.run.id, world.attempt)

    assert line.ok is False
    assert line.text == "no tracer wired"


def test_trace_line_passes_when_observed() -> None:
    world = World()

    line = _trace_line(world.ports(), world.run.id, world.attempt)

    assert line.ok is True
    assert line.text == f"spans observed for attempt {world.attempt.id}"


# ── `_spend_line` ────────────────────────────────────────────────────────────────────────


def test_spend_line_fails_with_no_attempt() -> None:
    world = World()

    line = _spend_line(world.ports(), world.run.id, None)

    assert line.ok is False
    assert line.text == "no attempt recorded"


def test_spend_line_fails_with_no_gateway_wired() -> None:
    world = World()

    line = _spend_line(world.ports(gateway=None), world.run.id, world.attempt)

    assert line.ok is False
    assert line.text == "no gateway wired"


def test_spend_line_fails_when_calls_is_zero_even_if_not_provisional() -> None:
    world = World()
    world.gateway.script(
        world.run.id,
        world.attempt.id,
        AttemptSpend(
            usd=Decimal("0"), tokens_in=0, tokens_out=0, by_model=(), calls=0, provisional=False
        ),
    )

    line = _spend_line(world.ports(), world.run.id, world.attempt)

    assert line.ok is False


def test_spend_line_passes_when_settled_with_calls() -> None:
    world = World()

    line = _spend_line(world.ports(), world.run.id, world.attempt)

    assert line.ok is True
    assert line.text == "3 calls attributed"


# ── `_verify_line` ───────────────────────────────────────────────────────────────────────


def test_verify_line_fails_with_no_row() -> None:
    assert _verify_line(None).ok is False


def test_verify_line_passes_when_done() -> None:
    world = World()

    assert _verify_line(world.verify_row).ok is True


# ── `_run_done_line` ─────────────────────────────────────────────────────────────────────


def test_run_done_line_passes_when_done() -> None:
    world = World()

    assert _run_done_line(world.run).ok is True


@pytest.mark.parametrize("status", ["failed", "cancelled", "running", "needs_you"])
def test_run_done_line_fails_for_every_other_status(status: str) -> None:
    world = World()
    run = world.run.model_copy(update={"status": status})

    line = _run_done_line(run)

    assert line.ok is False
    assert line.text == f"run finished {status}"
