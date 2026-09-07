"""`application/steps/plan_check.py`: the `plan.check` kind's whole behaviour (AD-7, FR-8).

Every list file the planner recorded (`Run.plan_refs`, copied into this row's own
`with_resolved` by `plan_check_row`) is re-read at its branch's current head and compared
by content, not by commit — the module docstring's own reasoning for why. `resume_signal
continue` never touches `Git` at all: AD-13's own effect for `plan_stale` is "the recorded
plan proceeds".
"""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext, StepExecutor, StepPorts
from orchestrator.application.steps.plan_check import PlanCheckExecutor
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit

WORK_DIR = "/work"
URL = "https://example.test/org/repo.git"
BASE_DIR = "/work/proj/repo/base"
BASE_BRANCH = "main"
STORIES_PATH = "epics/epic-1/stories.yaml"
OLD_SHA = "old0000000000000000000000000000000000000"
NEW_SHA = "new0000000000000000000000000000000000000"


def a_row(*, with_resolved: dict[str, object]) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=new_id(),
        seq=1,
        path="plan",
        label="plan",
        kind="plan.check",
        gate="deterministic",
        status="running",
        with_resolved=with_resolved,
    )


def with_resolved(
    *,
    plan_refs: dict[str, str] | None = None,
    list_branches: dict[str, str | None] | None = None,
    base_branch: str = BASE_BRANCH,
) -> dict[str, object]:
    return {
        "timeout_min": 5,
        "base_dir": BASE_DIR,
        "url": URL,
        "base_branch": base_branch,
        "plan_refs": plan_refs or {},
        "list_branches": list_branches or {},
    }


def a_context(
    row: StepRun, git: FakeGit, *, resume_signal: GateRecord | None = None
) -> StepContext:
    return StepContext(
        row=row,
        with_resolved=row.with_resolved,
        cwd=None,
        frame_start_sha=None,
        previous_attempt=None,
        attempt=Attempt(id=new_id(), run_id=row.run_id, step_run_id=row.id, n=1, status="running"),
        resume_signal=resume_signal,
        ports=StepPorts(git=git, clock=FakeClock(EPOCH), work_dir=WORK_DIR),
    )


def a_gate_record(row: StepRun, *, event: str) -> GateRecord:
    return GateRecord(
        id=new_id(), run_id=row.run_id, at=EPOCH, path=row.path, event=event, actor="operator"
    )


def test_the_executor_satisfies_the_protocol() -> None:
    assert isinstance(PlanCheckExecutor(), StepExecutor)


def test_a_plan_with_no_list_files_is_done_without_reaching_git() -> None:
    """`repo-init@1`: no `for_each`, so `plan_refs` is empty (AD-7)."""
    row = a_row(with_resolved=with_resolved())
    git = FakeGit()

    result = PlanCheckExecutor().execute(a_context(row, git))

    assert result.status == "done"
    assert result.park is None
    assert git.calls == []


def test_identical_content_at_the_branch_head_is_done() -> None:
    row = a_row(
        with_resolved=with_resolved(
            plan_refs={STORIES_PATH: OLD_SHA},
            list_branches={STORIES_PATH: "epic/1"},
        )
    )
    git = FakeGit(
        refs={"epic/1": NEW_SHA},
        files={(OLD_SHA, STORIES_PATH): "- id: 1\n", (NEW_SHA, STORIES_PATH): "- id: 1\n"},
    )

    result = PlanCheckExecutor().execute(a_context(row, git))

    assert result.status == "done"
    assert result.park is None


def test_different_content_at_the_branch_head_parks_plan_stale() -> None:
    row = a_row(
        with_resolved=with_resolved(
            plan_refs={STORIES_PATH: OLD_SHA},
            list_branches={STORIES_PATH: "epic/1"},
        )
    )
    git = FakeGit(
        refs={"epic/1": NEW_SHA},
        files={(OLD_SHA, STORIES_PATH): "- id: 1\n", (NEW_SHA, STORIES_PATH): "- id: 2\n"},
    )

    result = PlanCheckExecutor().execute(a_context(row, git))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "plan_stale"
    assert result.park.reason == f"plan stale: {STORIES_PATH}"
    assert result.park.path == "plan"
    assert result.reason == f"plan stale: {STORIES_PATH}"


def test_a_branch_recorded_as_none_falls_back_to_the_base_branch() -> None:
    """`initiative@1`'s root frame names no branch: `plan_ref` itself reads the base one."""
    row = a_row(
        with_resolved=with_resolved(
            plan_refs={"epics.yaml": OLD_SHA},
            list_branches={"epics.yaml": None},
            base_branch="main",
        )
    )
    git = FakeGit(
        refs={"main": NEW_SHA},
        files={(OLD_SHA, "epics.yaml"): "same", (NEW_SHA, "epics.yaml"): "same"},
    )

    result = PlanCheckExecutor().execute(a_context(row, git))

    assert result.status == "done"
    assert git.called("ls_remote") == [(URL, "main")]


def test_a_branch_the_remote_no_longer_holds_is_stale() -> None:
    row = a_row(
        with_resolved=with_resolved(
            plan_refs={STORIES_PATH: OLD_SHA},
            list_branches={STORIES_PATH: "epic/1"},
        )
    )
    git = FakeGit(refs={}, files={(OLD_SHA, STORIES_PATH): "- id: 1\n"})

    result = PlanCheckExecutor().execute(a_context(row, git))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "plan_stale"


def test_the_first_stale_path_in_sorted_order_is_the_one_named() -> None:
    row = a_row(
        with_resolved=with_resolved(
            plan_refs={"b.yaml": OLD_SHA, "a.yaml": OLD_SHA},
            list_branches={"b.yaml": "main", "a.yaml": "main"},
        )
    )
    git = FakeGit(
        refs={"main": NEW_SHA},
        files={
            (OLD_SHA, "a.yaml"): "same",
            (NEW_SHA, "a.yaml"): "same",
            (OLD_SHA, "b.yaml"): "old",
            (NEW_SHA, "b.yaml"): "new",
        },
    )

    result = PlanCheckExecutor().execute(a_context(row, git))

    assert result.park is not None
    assert result.park.reason == "plan stale: b.yaml"


def test_a_continue_signal_is_done_without_re_reading_anything() -> None:
    row = a_row(
        with_resolved=with_resolved(
            plan_refs={STORIES_PATH: OLD_SHA},
            list_branches={STORIES_PATH: "epic/1"},
        )
    )
    git = FakeGit()

    result = PlanCheckExecutor().execute(
        a_context(row, git, resume_signal=a_gate_record(row, event="continue"))
    )

    assert result.status == "done"
    assert result.park is None
    assert git.calls == []


def test_a_resume_signal_of_a_different_kind_still_checks() -> None:
    """Only `continue` short-circuits; a `retry` (unreachable in practice) still checks."""
    row = a_row(with_resolved=with_resolved())
    git = FakeGit()

    result = PlanCheckExecutor().execute(
        a_context(row, git, resume_signal=a_gate_record(row, event="retry"))
    )

    assert result.status == "done"
