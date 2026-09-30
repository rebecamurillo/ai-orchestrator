"""`evaluate` finds the readiness Run's rows by kind, never by the shipped step ids.

Operator decision 2026-09-30: the orchestrator hardcodes no template name and no template
step id; it follows the workflow and triggers actions. Rows are found by kind, never by the
shipped exemplar's step ids. Before this, `_lines` matched `row.path.endswith(".build")` and
`".verify"` — the step ids of `templates/story.yaml` — so a readiness Template whose story
was split as plan/implement/verify/review reported `build row is not done` forever and no
harness could ever be enabled.

Three facts, each on its own fixture copy: (a) a Run whose agent row is `implement` and shell
row `check` evaluates exactly like one named `build`/`verify`; (b) with two `done` agent rows
(`plan`, then `implement`) every attempt-fed line reads the later one's attempt, because that
is the `end_sha` where the story file's `status: done` is observable; (c) with no `done` agent
row the first line still says `build row is not done`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from orchestrator.application.use_cases.harness_readiness import (
    READINESS_SPEC_FOLDER,
    READINESS_STORY_ID,
)
from orchestrator.application.use_cases.harness_readiness_evaluate import (
    CHECK_STORY_FILE_DONE,
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

NOW = datetime(2026, 9, 30, tzinfo=UTC)
WORK_DIR = Path("/work")
STORIES_DIR = f"{READINESS_SPEC_FOLDER}/stories"
STORY_FILE = f"{STORIES_DIR}/{READINESS_STORY_ID}-create-hello.md"
DONE_STORY = "---\nstatus: done\n---\n\nbody\n"
OPEN_STORY = "---\nstatus: in-progress\n---\n\nbody\n"
PLAN_SHA = "a" * 40
IMPLEMENT_SHA = "b" * 40

#: The kinds the planner writes, as `application/steps` names them — never a step id.
AGENT = "agent"
SHELL = "shell"


class World:
    """A `done` readiness Run whose rows this test names however it likes; every port wired
    and passing by default, and one attempt per agent row."""

    def __init__(self, rows: list[tuple[str, str, str]]) -> None:
        """`rows` are `(step id, kind, status)` in `seq` order."""
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
            quality_gate_command="sh check.sh",
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
            template_name="readiness-fixture",
            template_version=1,
            inputs={"harness": "claude", "branch": "readiness/claude/2026-09-30"},
            status="done",
            budget_usd=Decimal("5"),
            created_at=NOW,
        )
        self.rows = [
            StepRun(
                id=new_id(),
                run_id=self.run.id,
                seq=seq,
                path=f"stories[0].{step_id}",
                label=f"story 1 · {step_id}",
                kind=kind,
                gate="liveness" if kind == AGENT else "deterministic",
                status=status,  # type: ignore[arg-type]
            )
            for seq, (step_id, kind, status) in enumerate(rows, start=1)
        ]
        self.attempts: dict[str, Attempt] = {}
        self.tracer = FakeTracer()
        self.gateway = FakeGateway()
        self.git = FakeGit(files={}, listings={})
        self.uow = FakeUnitOfWork()

    def row(self, step_id: str) -> StepRun:
        return next(row for row in self.rows if row.path.endswith(f".{step_id}"))

    def attempt_for(self, step_id: str, *, end_sha: str, story: str = DONE_STORY) -> Attempt:
        """One `done` attempt on that row, observed, settled, and with a story file at its
        `end_sha` — each agent row leaves its own commit behind."""
        attempt = Attempt(
            id=new_id(),
            run_id=self.run.id,
            step_run_id=self.row(step_id).id,
            n=1,
            status="done",
            session_id=f"sess-{step_id}",
            end_sha=end_sha,
        )
        self.attempts[step_id] = attempt
        self.tracer.observed[(self.run.id, attempt.id)] = True
        self.gateway.script(
            self.run.id,
            attempt.id,
            AttemptSpend(
                usd=Decimal("1"),
                tokens_in=1,
                tokens_out=1,
                by_model=(),
                calls=len(self.attempts),
                provisional=False,
            ),
        )
        self.git.files[(end_sha, STORY_FILE)] = story
        self.git.listings[(end_sha, STORIES_DIR)] = [STORY_FILE]
        return attempt

    def evaluate(self) -> Harness:
        ports = HarnessEvaluatePorts(
            runs=FakeRunRepository([self.run]),
            steps=FakeStepRunRepository(self.rows),
            attempts=FakeAttemptRepository(list(self.attempts.values())),
            harnesses=FakeHarnessRepository([Harness(name="claude", version_pin="2.1.258")]),
            projects=FakeProjectRepository([self.project]),
            repositories=FakeRepositoryRepository([self.repository]),
            uow=self.uow,
            clock=FakeClock(NOW),
            work_dir=WORK_DIR,
            git=self.git,
            tracer=self.tracer,
            gateway=self.gateway,
        )
        with self.uow:
            updated = evaluate(ports, self.run.id)
        assert updated is not None
        return updated


def lines_of(harness: Harness) -> list[tuple[str, bool, str]]:
    return [(line.check, line.ok, line.text) for line in harness.lines]


# ── (a) the step ids do not matter ───────────────────────────────────────────────────────


def test_rows_named_implement_and_check_evaluate_exactly_like_build_and_verify() -> None:
    shipped = World([("build", AGENT, "done"), ("verify", SHELL, "done")])
    shipped.attempt_for("build", end_sha=IMPLEMENT_SHA)
    renamed = World([("implement", AGENT, "done"), ("check", SHELL, "done")])
    renamed.attempt_for("implement", end_sha=IMPLEMENT_SHA)

    shipped_result = shipped.evaluate()
    renamed_result = renamed.evaluate()

    assert renamed_result.enabled is True
    assert renamed_result.failing_check is None
    # the `session` text names the attempt's own session id, which differs by fixture name
    # only because the fixture derives it from the step id; everything else is identical
    assert [(check, ok) for check, ok, _text in lines_of(renamed_result)] == [
        (check, ok) for check, ok, _text in lines_of(shipped_result)
    ]
    assert lines_of(renamed_result)[1][2] == "session sess-implement"


def test_a_shell_row_named_check_is_the_verify_row() -> None:
    world = World([("implement", AGENT, "done"), ("check", SHELL, "error")])
    world.attempt_for("implement", end_sha=IMPLEMENT_SHA)

    updated = world.evaluate()

    assert updated.enabled is False
    assert updated.failing_check == "verify exit 0: verify did not pass"


# ── (b) several agent rows: the last done one is the build row ───────────────────────────


def test_with_plan_then_implement_done_every_line_reads_the_implement_attempt() -> None:
    world = World(
        [("plan", AGENT, "done"), ("implement", AGENT, "done"), ("verify", SHELL, "done")]
    )
    # `plan` committed a story file still in progress; `implement` is where it reached done
    plan = world.attempt_for("plan", end_sha=PLAN_SHA, story=OPEN_STORY)
    implement = world.attempt_for("implement", end_sha=IMPLEMENT_SHA)

    updated = world.evaluate()

    assert updated.enabled is True
    assert lines_of(updated)[0] == (CHECK_STORY_FILE_DONE, True, "status: done")
    assert lines_of(updated)[1][2] == f"session {implement.session_id}"
    assert lines_of(updated)[2][2] == f"spans observed for attempt {implement.id}"
    assert lines_of(updated)[3][2] == "2 calls attributed"
    assert world.tracer.observed_calls == [(world.run.id, implement.id, None)]
    assert plan.id not in {call[1] for call in world.tracer.observed_calls}


def test_a_later_agent_row_that_did_not_finish_does_not_displace_the_done_one() -> None:
    """`review` errored after `implement` ended done: the build row is still `implement`,
    the last agent row that *finished* — the Run's own `error` is the sixth line's to say."""
    world = World(
        [
            ("implement", AGENT, "done"),
            ("verify", SHELL, "done"),
            ("review", AGENT, "error"),
        ]
    )
    implement = world.attempt_for("implement", end_sha=IMPLEMENT_SHA)

    updated = world.evaluate()

    assert lines_of(updated)[0] == (CHECK_STORY_FILE_DONE, True, "status: done")
    assert lines_of(updated)[1][2] == f"session {implement.session_id}"


def test_the_last_shell_row_is_the_verify_row_when_there_are_several() -> None:
    """A Template that runs a `lint` shell row before `verify`: the gate the readiness line
    reports is the last one in `seq` order."""
    world = World(
        [("implement", AGENT, "done"), ("lint", SHELL, "done"), ("verify", SHELL, "error")]
    )
    world.attempt_for("implement", end_sha=IMPLEMENT_SHA)

    updated = world.evaluate()

    assert updated.failing_check == "verify exit 0: verify did not pass"


# ── (c) no done agent row ────────────────────────────────────────────────────────────────


def test_with_no_done_agent_row_the_first_line_says_build_row_is_not_done() -> None:
    """Neither agent row finished: the fallback is the last agent row of whatever status, so
    the line says what it always said rather than reading as "no row at all"."""
    world = World(
        [("plan", AGENT, "blocked"), ("implement", AGENT, "error"), ("verify", SHELL, "done")]
    )
    world.attempt_for("plan", end_sha=PLAN_SHA)

    updated = world.evaluate()

    assert updated.enabled is False
    assert updated.failing_check == f"{CHECK_STORY_FILE_DONE}: build row is not done"


def test_with_no_agent_row_at_all_the_first_line_says_build_row_is_not_done() -> None:
    world = World([("verify", SHELL, "done")])

    updated = world.evaluate()

    assert updated.enabled is False
    assert updated.failing_check == f"{CHECK_STORY_FILE_DONE}: build row is not done"
