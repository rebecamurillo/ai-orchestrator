"""`evaluate`'s fifth line when the Repository declares no quality gate (SPEC CAP-8).

The readiness fixture declares none (`harness_readiness_seed.py`), so the planner writes
its `verify` row `skipped · no quality_gate_command` and no gate ever runs. That must not
read as a failure — otherwise no harness can reach `enabled` — and it must not read as
`verify exit 0` either, because nothing exited 0. Those are two different assertions and
this module makes both: the line is `ok`, and it is called `no quality gate to run`.

The distinction is drawn on the row's own planner-written `reason`, not on the status
alone: a `verify` row skipped for any other reason — `skipped by operator`, say — is still
a readiness failure and still says `verify exit 0: verify did not pass`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.application.templates.plan_model import (
    REASON_ALREADY_DONE,
    REASON_NO_QUALITY_GATE,
)
from orchestrator.application.use_cases.harness_readiness import (
    READINESS_SPEC_FOLDER,
    READINESS_STORY_ID,
)
from orchestrator.application.use_cases.harness_readiness_evaluate import (
    CHECK_NO_QUALITY_GATE,
    CHECK_RUN_DONE,
    CHECK_SESSION_ID,
    CHECK_SPEND_ATTRIBUTABLE,
    CHECK_STORY_FILE_DONE,
    CHECK_TRACE_OBSERVED,
    CHECK_VERIFY_EXIT_0,
    HarnessEvaluatePorts,
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
END_SHA = "e" * 40
STORY_FILE = f"{READINESS_SPEC_FOLDER}/stories/{READINESS_STORY_ID}-create-hello.md"
DONE_STORY = "---\nstatus: done\n---\n\nbody\n"

#: What the fifth line says when there was no gate: the planner's own two words, joined the
#: way every other `skipped` row is rendered.
SKIPPED_TEXT = f"skipped · {REASON_NO_QUALITY_GATE}"


def a_verify_row(*, status: str, reason: str | None) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=new_id(),
        seq=2,
        path="stories[0].verify",
        label="story 1 · verify",
        kind="shell",
        gate="deterministic",
        status=status,  # type: ignore[arg-type]
        reason=reason,
    )


# ── `_verify_line` on its own ────────────────────────────────────────────────────────────


def test_a_skipped_row_with_no_quality_gate_is_ok() -> None:
    line = _verify_line(a_verify_row(status="skipped", reason=REASON_NO_QUALITY_GATE))

    assert line.ok is True


def test_that_line_does_not_claim_a_gate_exited_zero() -> None:
    """The honesty assertion: `enabled` may not be bought with a check that never ran."""
    line = _verify_line(a_verify_row(status="skipped", reason=REASON_NO_QUALITY_GATE))

    assert line.check == CHECK_NO_QUALITY_GATE
    assert line.check != CHECK_VERIFY_EXIT_0
    assert line.text == SKIPPED_TEXT


def test_a_done_row_still_reads_as_the_gate_it_ran() -> None:
    line = _verify_line(a_verify_row(status="done", reason=None))

    assert line.check == CHECK_VERIFY_EXIT_0
    assert line.ok is True
    assert line.text == "verify exited 0"


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("skipped", None),
        ("skipped", "skipped by operator"),
        ("skipped", REASON_ALREADY_DONE),
        ("error", None),
        ("blocked", None),
    ],
)
def test_any_other_unrun_verify_is_still_a_readiness_failure(
    status: str, reason: str | None
) -> None:
    line = _verify_line(a_verify_row(status=status, reason=reason))

    assert line.ok is False
    assert line.check == CHECK_VERIFY_EXIT_0
    assert line.text == "verify did not pass"


# ── `evaluate` over a Run of the seeded fixture ──────────────────────────────────────────


class World:
    """A readiness Run that finished `done` with its `verify` row planned away — the shape
    every Run on the seeded fixture now has."""

    def __init__(self, *, verify_reason: str | None = REASON_NO_QUALITY_GATE) -> None:
        self.project = Project(
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
        self.repository = Repository(
            id=new_id(),
            project_id=self.project.id,
            slug="readiness-repo",
            url="file:///work/readiness/origin.git",
            default_branch="main",
            install_command="",
            quality_gate_command="",
            unit_test_command="",
            test_globs=(),
            package_manager="other",
            clone_check=CloneCheck.pending(),
            created_at=NOW,
            updated_at=NOW,
        )
        self.run = Run(
            id=new_id(),
            project_id=self.project.id,
            repository_id=self.repository.id,
            template_name="epic",
            template_version=1,
            inputs={"harness": "claude", "branch": "readiness/claude/2026-03-04"},
            status="done",
            budget_usd=Decimal("5"),
            created_at=NOW,
        )
        self.build_row = StepRun(
            id=new_id(),
            run_id=self.run.id,
            seq=1,
            path="stories[0].build",
            label="story 1 · build",
            kind="agent",
            gate="liveness",
            status="done",
        )
        self.verify_row = a_verify_row(status="skipped", reason=verify_reason).model_copy(
            update={"run_id": self.run.id}
        )
        self.attempt = Attempt(
            id=new_id(),
            run_id=self.run.id,
            step_run_id=self.build_row.id,
            n=1,
            status="done",
            session_id="sess-42",
            end_sha=END_SHA,
        )
        self.uow = FakeUnitOfWork()
        self.harnesses = FakeHarnessRepository([Harness(name="claude", version_pin="2.1.258")])
        self.tracer = FakeTracer()
        self.tracer.observed[(self.run.id, self.attempt.id)] = True
        self.gateway = FakeGateway()
        self.gateway.script(
            self.run.id,
            self.attempt.id,
            AttemptSpend(
                usd=Decimal("1"),
                tokens_in=1,
                tokens_out=1,
                by_model=(),
                calls=2,
                provisional=False,
            ),
        )
        self.ports = HarnessEvaluatePorts(
            runs=FakeRunRepository([self.run]),
            steps=FakeStepRunRepository([self.build_row, self.verify_row]),
            attempts=FakeAttemptRepository([self.attempt]),
            harnesses=self.harnesses,
            projects=FakeProjectRepository([self.project]),
            repositories=FakeRepositoryRepository([self.repository]),
            uow=self.uow,
            clock=FakeClock(NOW),
            work_dir=WORK_DIR,
            git=FakeGit(
                files={(END_SHA, STORY_FILE): DONE_STORY},
                listings={(END_SHA, f"{READINESS_SPEC_FOLDER}/stories"): [STORY_FILE]},
            ),
            tracer=self.tracer,
            gateway=self.gateway,
        )

    def evaluate(self) -> Harness | None:
        with self.uow:
            return evaluate(self.ports, self.run.id)


def test_a_readiness_run_with_no_gate_to_run_enables_the_harness() -> None:
    updated = World().evaluate()

    assert updated is not None
    assert updated.enabled is True
    assert updated.failing_check is None


def test_the_six_lines_name_the_absent_gate_in_the_fifth_slot() -> None:
    updated = World().evaluate()

    assert updated is not None
    assert [(line.check, line.ok) for line in updated.lines] == [
        (CHECK_STORY_FILE_DONE, True),
        (CHECK_SESSION_ID, True),
        (CHECK_TRACE_OBSERVED, True),
        (CHECK_SPEND_ATTRIBUTABLE, True),
        (CHECK_NO_QUALITY_GATE, True),
        (CHECK_RUN_DONE, True),
    ]
    assert updated.lines[4].text == SKIPPED_TEXT


def test_a_verify_skipped_by_the_operator_still_disables() -> None:
    updated = World(verify_reason="skipped by operator").evaluate()

    assert updated is not None
    assert updated.enabled is False
    assert updated.failing_check == "verify exit 0: verify did not pass"
