"""`board_view` and `run_detail` — the Board and Run detail read models (4.12, SPEC CAP-12).

Each I/O-matrix row of the story spec is one test here: every Run status appears once on
the Board, in the right column, with the right token; progress is computed only for an
`epic`/`initiative` Run and is `None` otherwise; a retried row's `StepRow.attempts` and
`latest` are right; a `done` Run's `summary` lists what it should.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.application.rules.signals import run_admitted_signals
from orchestrator.application.use_cases.create_run import RunReadPorts
from orchestrator.application.use_cases.run_views import (
    RunViewPorts,
    _bracket_index,
    board_view,
    run_detail,
    run_graph_for,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.statuses import RunStatus, StepStatus
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-0000000000a1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-0000000000b1")
ATTEMPT_COUNT = 3
TOKENS_IN = 100
TOKENS_OUT = 50


def project() -> Project:
    return Project(
        id=PROJECT_ID,
        slug="acme",
        name="Acme",
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=NOW,
        updated_at=NOW,
    )


def repository() -> Repository:
    return Repository(
        id=REPOSITORY_ID,
        project_id=PROJECT_ID,
        slug="acme-app",
        url="https://example.invalid/acme/app.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=(),
        package_manager="uv",
        clone_check=CloneCheck(status="ok", at=NOW, output="", bmad_version="6.11.0"),
        created_at=NOW,
        updated_at=NOW,
    )


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT_ID,
        "repository_id": REPOSITORY_ID,
        "template_name": "repo-init",
        "template_version": 1,
        "inputs": {"base_branch": "main"},
        "status": "queued",
        "budget_usd": Decimal("10"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_row(  # noqa: PLR0913 — one keyword per `StepRun` field a test needs to vary
    run: Run,
    path: str,
    *,
    seq: int,
    status: StepStatus = "planned",
    kind: str = "shell",
    story_id: str | None = None,
) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run.id,
        seq=seq,
        path=path,
        label=path.rsplit(".", maxsplit=1)[-1],
        kind=kind,
        gate="deterministic",
        status=status,
        story_id=story_id,
    )


def a_commit_row(run: Run, path: str, *, seq: int, status: StepStatus, story_id: str) -> StepRun:
    """A `commit-guard` row: the kind `_progress`/`_story_cells` key their computation on."""
    return a_row(run, path, seq=seq, status=status, kind="git.commit", story_id=story_id)


class Harness:
    """One set of fakes, wired the way `api/providers.py::run_view_ports` wires the real
    adapters."""

    def __init__(self) -> None:
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.attempts = FakeAttemptRepository()
        self.gate_records = FakeGateRecordRepository()
        self.projects = FakeProjectRepository([project()])
        self.repositories = FakeRepositoryRepository([repository()])
        self.logs = FakeLogReader()
        self.clock = FakeClock(NOW)

    def ports(self) -> RunViewPorts:
        return RunViewPorts(
            runs=self.runs,
            steps=self.steps,
            attempts=self.attempts,
            gate_records=self.gate_records,
            projects=self.projects,
            repositories=self.repositories,
            logs=self.logs,
            clock=self.clock,
        )

    def board_ports(self) -> RunReadPorts:
        """`board_view` reads through this shape instead — see that function's own
        docstring for why it cannot share `RunViewPorts`."""
        return RunReadPorts(
            runs=self.runs,
            steps=self.steps,
            projects=self.projects,
            repositories=self.repositories,
            gate_records=self.gate_records,
        )


@pytest.fixture
def harness() -> Harness:
    return Harness()


# ── the Board ────────────────────────────────────────────────────────────────────────────


def test_every_run_status_lands_in_its_own_column(harness: Harness) -> None:
    statuses: list[RunStatus] = ["queued", "running", "needs_you", "done", "failed", "cancelled"]
    for status in statuses:
        extra: dict[str, object] = {"park_kind": "blocked"} if status == "needs_you" else {}
        harness.runs.add(a_run(status=status, **extra))

    view = board_view(harness.board_ports(), project_id=None, now=NOW)

    assert len(view.columns.queued) == 1
    assert len(view.columns.running) == 1
    assert len(view.columns.needs_you) == 1
    assert len(view.columns.done) == 1
    # cancelled files under failed, alongside the one real `failed` Run
    assert len(view.columns.failed) == 2  # noqa: PLR2004
    assert {card.token for card in view.columns.failed} == {"ERR", "CAN"}
    assert view.counts == view.counts.__class__(running=1, queued=1, needs_you=1)


def test_a_checkpoint_park_reads_chk_not_blk(harness: Harness) -> None:
    harness.runs.add(a_run(status="needs_you", park_kind="checkpoint"))

    view = board_view(harness.board_ports(), project_id=None, now=NOW)

    assert view.columns.needs_you[0].token == "CHK"


# `test_a_card_carries_the_runs_own_initiative_membership` and
# `test_a_card_off_a_run_started_on_its_own_carries_no_initiative` were here: Operator
# decision 2026-09-30 removed the fan-in Initiative feature entirely, and `Card` no longer
# carries `initiative`/`initiative_role` (those were `RunSummaryOut`'s own two fields,
# widened onto `Card` for S8; both are gone). The progress test below, which covers the
# `initiative` *template*'s epic/story counting — a surviving, unrelated feature — is
# unchanged.
def test_progress_for_an_initiative_run_counts_epics_and_stories(harness: Harness) -> None:
    """The story spec's own AC, verbatim: two epics, eight stories, three stories done, one
    epic pushed → `progress == {epics_done:1, epics_total:2, stories_done:3, stories_total:8,
    links:1}`."""
    run = a_run(
        template_name="initiative",
        status="running",
        compare_urls=("https://example.invalid/compare/epic-0",),
    )
    harness.runs.add(run)
    seq = 1

    def next_seq() -> int:
        nonlocal seq
        seq += 1
        return seq - 1

    rows = [a_row(run, "epics[0].checkout", seq=next_seq(), status="done")]
    for i, status in enumerate(("done", "done", "done", "planned")):
        rows.append(
            a_commit_row(
                run,
                f"epics[0].stories[{i}].commit-guard",
                seq=next_seq(),
                status=status,
                story_id=f"e0s{i}",
            )
        )
    rows.append(a_row(run, "epics[0].push", seq=next_seq(), status="done", kind="git.push"))
    for i, status in enumerate(("planned", "planned", "planned", "running")):
        rows.append(
            a_commit_row(
                run,
                f"epics[1].stories[{i}].commit-guard",
                seq=next_seq(),
                status=status,
                story_id=f"e1s{i}",
            )
        )
    rows.append(a_row(run, "epics[1].push", seq=next_seq(), status="planned", kind="git.push"))
    harness.steps.add_many(rows)

    view = board_view(harness.board_ports(), project_id=None, now=NOW)
    card = view.columns.running[0]

    assert card.progress is not None
    assert card.progress.epics_done == 1
    assert card.progress.epics_total == 2  # noqa: PLR2004
    assert card.progress.stories_done == 3  # noqa: PLR2004
    assert card.progress.stories_total == 8  # noqa: PLR2004
    assert card.progress.links == 1
    assert card.current_step_label == "commit-guard"


def test_progress_is_none_for_a_plan_with_no_story_frame(harness: Harness) -> None:
    """Operator decision 2026-09-30: no template name hardcoded in product code. A plan with
    no `stories[n]` frame anywhere carries no progress, whatever its Template is called —
    and the card names that Template instead of showing a blank segment."""
    run = a_run(template_name="house-init")
    harness.runs.add(run)
    harness.steps.add_many(
        [
            a_row(run, "checkout", seq=1, status="done"),
            a_row(run, "commit", seq=2, status="done", kind="git.commit"),
        ]
    )

    view = board_view(harness.board_ports(), project_id=None, now=NOW)

    assert view.columns.queued[0].progress is None
    assert view.columns.queued[0].kind_label == "house-init"


def test_a_card_with_progress_carries_no_kind_label(harness: Harness) -> None:
    """The two are alternatives on the card, never both — which is what the old two-entry
    lookup table said by having no row for a Template that shows progress."""
    run = a_run(template_name="house-epic")
    harness.runs.add(run)
    harness.steps.add_many(
        [a_commit_row(run, "stories[0].commit-guard", seq=1, status="done", story_id="1")]
    )

    view = board_view(harness.board_ports(), project_id=None, now=NOW)

    assert view.columns.queued[0].progress is not None
    assert view.columns.queued[0].kind_label is None


def test_current_step_label_prefers_running_then_park_then_last_done(harness: Harness) -> None:
    run = a_run(status="needs_you", park_kind="blocked")
    run = run.model_copy(update={"park_path": "install"})
    harness.runs.add(run)
    harness.steps.add_many(
        [
            a_row(run, "checkout", seq=1, status="done"),
            a_row(run, "install", seq=2, status="blocked"),
            a_row(run, "commit", seq=3, status="planned", kind="git.commit"),
        ]
    )

    view = board_view(harness.board_ports(), project_id=None, now=NOW)

    assert view.columns.needs_you[0].current_step_label == "install"


def test_needs_you_since_reads_the_matching_gate_record(harness: Harness) -> None:
    run = a_run(status="needs_you", park_kind="blocked")
    harness.runs.add(run)
    harness.gate_records.add(
        GateRecord(id=new_id(), run_id=run.id, at=NOW, event="blocked", actor="machine")
    )

    view = board_view(harness.board_ports(), project_id=None, now=NOW)

    assert view.columns.needs_you[0].needs_you_since == NOW


def test_project_filter_scopes_the_board(harness: Harness) -> None:
    other_project = UUID("01960000-0000-7000-9000-0000000000a9")
    harness.runs.add(a_run(project_id=PROJECT_ID))
    harness.runs.add(a_run(project_id=other_project))

    view = board_view(harness.board_ports(), project_id=PROJECT_ID, now=NOW)

    assert len(view.columns.queued) == 1


# ── the Run detail ───────────────────────────────────────────────────────────────────────


def test_unknown_run_is_not_found(harness: Harness) -> None:
    with pytest.raises(NotFound):
        run_detail(harness.ports(), new_id())


def test_a_row_with_three_attempts_reports_them_and_the_last_forty_log_lines(
    harness: Harness,
) -> None:
    run = a_run(status="running")
    harness.runs.add(run)
    row = a_row(run, "build", seq=1, status="running", kind="agent")
    harness.steps.add_many([row])
    for n in range(1, ATTEMPT_COUNT + 1):
        harness.attempts.add(
            Attempt(
                id=new_id(),
                run_id=run.id,
                step_run_id=row.id,
                n=n,
                status="error" if n < ATTEMPT_COUNT else "running",
                log_path=f"/work/logs/{n}.log",
            )
        )
    harness.logs.lines_by_path[f"/work/logs/{ATTEMPT_COUNT}.log"] = [f"line {i}" for i in range(50)]

    detail = run_detail(harness.ports(), run.id)

    step_row = detail.steps[0]
    assert step_row.attempts == ATTEMPT_COUNT
    assert step_row.latest is not None
    assert step_row.latest.n == ATTEMPT_COUNT
    assert step_row.latest.log_tail == [f"line {i}" for i in range(10, 50)]


def test_admitted_signals_matches_the_park(harness: Harness) -> None:
    """The park row's own `kind` is looked up and threaded into `run_admitted_signals` —
    the same computation `RunSummaryOut.of(run, park_row_kind=...)` (4.9) already makes,
    now made by this read model instead of the router."""
    run = a_run(status="needs_you", park_kind="verify_failed", park_path="build")
    harness.runs.add(run)
    harness.steps.add_many([a_row(run, "build", seq=1, status="error", kind="agent")])

    detail = run_detail(harness.ports(), run.id)

    assert detail.admitted_signals == run_admitted_signals(run, "agent")
    assert "retry" in detail.admitted_signals


def test_a_budget_park_on_a_finished_row_offers_no_skip_step(harness: Harness) -> None:
    """The parked row's `status` is threaded beside its `kind` (Operator, 2026-09-26), so the
    Run detail offers only what `validate` would admit: a `budget` park is stamped onto the
    row that has just ended `done`, and `skip_step` needs `blocked`, `checkpoint` or `error`.
    """
    run = a_run(status="needs_you", park_kind="budget", park_path="build")
    harness.runs.add(run)
    harness.steps.add_many([a_row(run, "build", seq=1, status="done", kind="agent")])

    detail = run_detail(harness.ports(), run.id)

    assert detail.admitted_signals == ("budget_raise", "cancel")


def test_a_done_run_with_a_skipped_story_reports_it_and_the_links(harness: Harness) -> None:
    run = a_run(
        template_name="epic",
        status="done",
        compare_urls=("https://example.invalid/compare/1",),
    )
    harness.runs.add(run)
    harness.steps.add_many(
        [
            a_commit_row(run, "stories[0].commit-guard", seq=1, status="done", story_id="4-1"),
            a_commit_row(run, "stories[1].commit-guard", seq=2, status="skipped", story_id="4-2"),
        ]
    )

    detail = run_detail(harness.ports(), run.id)

    assert detail.summary is not None
    assert detail.summary.skipped == ["4-2"]
    assert detail.summary.links == ["https://example.invalid/compare/1"]


def test_summary_is_none_off_a_terminal_done_status(harness: Harness) -> None:
    run = a_run(status="running")
    harness.runs.add(run)
    harness.steps.add_many([a_row(run, "checkout", seq=1, status="running")])

    detail = run_detail(harness.ports(), run.id)

    assert detail.summary is None


def test_alert_is_none_unless_the_run_is_parked(harness: Harness) -> None:
    run = a_run(status="running")
    harness.runs.add(run)
    harness.steps.add_many([a_row(run, "checkout", seq=1, status="running")])

    detail = run_detail(harness.ports(), run.id)

    assert detail.alert is None


def test_alert_carries_the_token_reason_and_park_kind(harness: Harness) -> None:
    run = a_run(status="needs_you", park_kind="checkpoint", park_reason="story checkpoint")
    harness.runs.add(run)
    harness.steps.add_many([a_row(run, "build", seq=1, status="checkpoint", kind="agent")])

    detail = run_detail(harness.ports(), run.id)

    assert detail.alert is not None
    assert detail.alert.token == "CHK"
    assert detail.alert.reason == "story checkpoint"
    assert detail.alert.park_kind == "checkpoint"


def test_story_cells_reflect_each_frame_state(harness: Harness) -> None:
    run = a_run(template_name="epic", status="running", park_path=None)
    harness.runs.add(run)
    harness.steps.add_many(
        [
            a_commit_row(run, "stories[0].commit-guard", seq=1, status="done", story_id="4-1"),
            a_row(run, "stories[1].build", seq=2, status="running", kind="agent", story_id="4-2"),
            a_commit_row(run, "stories[1].commit-guard", seq=3, status="planned", story_id="4-2"),
            a_commit_row(run, "stories[2].commit-guard", seq=4, status="skipped", story_id="4-3"),
            a_commit_row(run, "stories[3].commit-guard", seq=5, status="planned", story_id="4-4"),
        ]
    )

    detail = run_detail(harness.ports(), run.id)

    states = {cell.story_id: cell.state for cell in detail.stories}
    assert states == {"4-1": "done", "4-2": "current", "4-3": "skipped", "4-4": "future"}


def test_cost_sums_tokens_across_every_attempt_and_uses_run_spend(harness: Harness) -> None:
    run = a_run(
        status="done",
        spend_usd=Decimal("1.500000"),
        started_at=NOW,
        ended_at=NOW,
    )
    harness.runs.add(run)
    row = a_row(run, "build", seq=1, status="done", kind="agent")
    harness.steps.add_many([row])
    harness.attempts.add(
        Attempt(
            id=new_id(),
            run_id=run.id,
            step_run_id=row.id,
            n=1,
            status="done",
            tokens_in=TOKENS_IN,
            tokens_out=TOKENS_OUT,
            cost_usd=Decimal("1.5"),
            cost_provisional=True,
        )
    )

    detail = run_detail(harness.ports(), run.id)

    assert detail.cost.spent_usd == Decimal("1.500000")
    assert detail.cost.tokens_in == TOKENS_IN
    assert detail.cost.tokens_out == TOKENS_OUT
    assert detail.cost.provisional is True
    assert detail.cost.trace_url is None


# ── branch coverage: the defensive/edge paths above ─────────────────────────────────────


def test_needs_you_since_is_none_when_gate_records_is_unwired() -> None:
    run = a_run(status="needs_you", park_kind="blocked")
    ports = RunReadPorts(runs=FakeRunRepository([run]))

    view = board_view(ports, project_id=None, now=NOW)

    assert view.columns.needs_you[0].needs_you_since is None


def test_latest_attempt_computes_seconds_when_both_timestamps_are_set(harness: Harness) -> None:
    run = a_run(status="running")
    harness.runs.add(run)
    row = a_row(run, "build", seq=1, status="done", kind="agent")
    harness.steps.add_many([row])
    ended = NOW.replace(minute=5)
    harness.attempts.add(
        Attempt(
            id=new_id(),
            run_id=run.id,
            step_run_id=row.id,
            n=1,
            status="done",
            started_at=NOW,
            ended_at=ended,
        )
    )

    detail = run_detail(harness.ports(), run.id)

    assert detail.steps[0].latest is not None
    assert detail.steps[0].latest.seconds == (ended - NOW).total_seconds()


def test_a_commit_kind_row_outside_any_story_frame_is_not_a_story_cell(harness: Harness) -> None:
    """`repo-init`'s own `commit` row is `git.commit`-kind but names no story — `_story_cells`
    skips it rather than fabricating a cell for a frame that does not exist."""
    run = a_run(template_name="repo-init", status="running")
    harness.runs.add(run)
    harness.steps.add_many([a_row(run, "commit", seq=1, status="done", kind="git.commit")])

    detail = run_detail(harness.ports(), run.id)

    assert detail.stories == []


def test_bracket_index_falls_back_to_zero_off_a_prefix_with_no_index() -> None:
    """Unreachable through `epic_frame` (it never returns a bracket-less prefix), kept as a
    total function rather than one that trusts its caller."""
    assert _bracket_index("epics") == 0


def test_cost_wall_clock_uses_the_latest_attempt_end_while_the_run_has_none(
    harness: Harness,
) -> None:
    run = a_run(status="running", started_at=NOW)
    harness.runs.add(run)
    row = a_row(run, "build", seq=1, status="done", kind="agent")
    harness.steps.add_many([row])
    ended = NOW.replace(minute=5)
    harness.attempts.add(
        Attempt(id=new_id(), run_id=run.id, step_run_id=row.id, n=1, status="done", ended_at=ended)
    )

    detail = run_detail(harness.ports(), run.id)

    assert detail.cost.wall_clock_seconds == (ended - NOW).total_seconds()


def test_cost_wall_clock_falls_back_to_now_when_nothing_has_ended(harness: Harness) -> None:
    run = a_run(status="running", started_at=NOW)
    harness.runs.add(run)
    row = a_row(run, "build", seq=1, status="running", kind="agent")
    harness.steps.add_many([row])

    detail = run_detail(harness.ports(), run.id)

    assert detail.cost.wall_clock_seconds == 0.0


# ── run_graph_for: the run graph route's one fetch ──────────────────────────────────────


def test_run_graph_for_builds_the_graph_of_a_known_run(harness: Harness) -> None:
    run = a_run(status="running")
    harness.runs.add(run)
    harness.steps.add_many([a_row(run, "checkout", seq=1, status="running")])

    graph = run_graph_for(harness.ports(), run.id)

    assert [node.id for node in graph.nodes] == ["root", "checkout"]


def test_run_graph_for_an_unknown_run_is_not_found(harness: Harness) -> None:
    with pytest.raises(NotFound):
        run_graph_for(harness.ports(), new_id())
