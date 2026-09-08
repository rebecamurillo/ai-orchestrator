"""The coverage the operator's anchor-conflict ruling requires alongside the two authorised
edits to `test_harnesses_router.py` and `tests/e2e/test_harnesses.py` (SPEC CAP-8): after a
real `evaluate()` run, `GET /harnesses`' `last_readiness_run_id` and `lines` carry the exact
values that run produced — not merely that the two keys are present.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from orchestrator.api.schemas.harnesses import HarnessOut
from orchestrator.application.use_cases.harness_readiness_evaluate import (
    HarnessEvaluatePorts,
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
END_SHA = "e" * 40
DONE_STORY = "---\nstatus: done\n---\n\nbody\n"
LINE_COUNT = 6


def test_get_harnesses_carries_the_exact_run_id_and_lines_evaluate_wrote() -> None:
    project = Project(
        id=new_id(),
        slug=READINESS_PROJECT_SLUG,
        name="Readiness",
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        builtin=True,
        created_at=NOW,
        updated_at=NOW,
    )
    repository = Repository(
        id=new_id(),
        project_id=project.id,
        slug="readiness-repo",
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
    run = Run(
        id=new_id(),
        project_id=project.id,
        repository_id=repository.id,
        template_name="epic",
        template_version=1,
        inputs={"harness": "claude", "branch": "readiness/claude/2026-03-04"},
        status="done",
        budget_usd=Decimal("5"),
        created_at=NOW,
    )
    build_row = StepRun(
        id=new_id(),
        run_id=run.id,
        seq=1,
        path="stories.1.story.build",
        label="build",
        kind="agent",
        gate="liveness",
        status="done",
    )
    verify_row = StepRun(
        id=new_id(),
        run_id=run.id,
        seq=2,
        path="stories.1.story.verify",
        label="verify",
        kind="shell",
        gate="deterministic",
        status="done",
    )
    attempt = Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=build_row.id,
        n=1,
        status="done",
        session_id="sess-42",
        end_sha=END_SHA,
    )
    harness = Harness(name="claude", version_pin="2.1.258")
    tracer = FakeTracer()
    tracer.observed[(run.id, attempt.id)] = True
    gateway = FakeGateway()
    gateway.script(
        run.id,
        attempt.id,
        AttemptSpend(
            usd=Decimal("1"), tokens_in=1, tokens_out=1, by_model=(), calls=2, provisional=False
        ),
    )
    git = FakeGit(
        files={(END_SHA, "specs/readiness/stories/1-create-hello.md"): DONE_STORY},
        listings={
            (END_SHA, "specs/readiness/stories"): ["specs/readiness/stories/1-create-hello.md"]
        },
    )
    ports = HarnessEvaluatePorts(
        runs=FakeRunRepository([run]),
        steps=FakeStepRunRepository([build_row, verify_row]),
        attempts=FakeAttemptRepository([attempt]),
        harnesses=FakeHarnessRepository([harness]),
        projects=FakeProjectRepository([project]),
        repositories=FakeRepositoryRepository([repository]),
        uow=FakeUnitOfWork(),
        clock=FakeClock(NOW),
        work_dir=Path("/work"),
        git=git,
        tracer=tracer,
        gateway=gateway,
    )

    with ports.uow:
        updated = evaluate(ports, run.id)
    assert updated is not None

    out = HarnessOut.of(updated)

    # the exact values `evaluate` wrote — not merely that the keys exist
    assert out.last_readiness_run_id == run.id
    assert out.enabled is True
    assert out.failing_check is None
    assert [(line.check, line.ok) for line in out.lines] == [
        ("story file done", True),
        ("session id recorded", True),
        ("trace observed", True),
        ("spend attributable", True),
        ("verify exit 0", True),
        ("run done", True),
    ]
    assert out.lines[1].text == "session sess-42"
    assert out.lines[3].text == "2 calls attributed"
    assert out.model_dump()["last_readiness_run_id"] == run.id
    assert len(out.model_dump()["lines"]) == LINE_COUNT
