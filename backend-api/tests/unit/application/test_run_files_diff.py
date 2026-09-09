"""`diff_run_file`: `GET /runs/{id}/files?path=&diff=1` (story 6-6, FR-31, AD-17).

The protected-path body links each file AD-17 flagged to its own unified diff, so the
Operator can judge the change before accepting it. Two things about this read are
deliberate and are what most of this module asserts:

**The scope is the park's own hit list, not the spec folder.** AD-17 protects `AGENTS.md`
wherever it is and every frozen test file, so every path this mode is asked about is outside
the Run's spec folder by construction. `read_run_file`'s `_within_spec_folder` would refuse
exactly the paths the mode exists for; the hit list is a *tighter* gate — the Run's own
record of what it stopped on — and the escape check is reused unchanged.

**The range starts at the parked attempt's `start_sha`**, the same "before the harness
started" end AD-17's own check measures from (`steps/agent_tail.py::_changes`), so what is
shown is exactly the change the Run stopped for.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.application.rules.protected_paths import hits_payload
from orchestrator.application.use_cases.run_files import RunFilesDiffPorts, diff_run_file
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import Forbidden, Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

NOW = datetime(2026, 9, 9, tzinfo=UTC)
BUILD = "stories[0].build"
WORKTREE = "/work/acme/widgets/wt/gates"
START_SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
AGENTS = "AGENTS.md"
TEST_FILE = "tests/api/test_runs.py"
UNIFIED = "diff --git a/AGENTS.md b/AGENTS.md\n@@ -1 +1 @@\n-old\n+new\n"
HITS = (Change(path=TEST_FILE, kind="modified"), Change(path=AGENTS, kind="added"))


class World:
    def __init__(  # noqa: PLR0913 — one keyword per fact a refusal case has to vary
        self,
        *,
        hits: tuple[Change, ...] = HITS,
        attempts: bool = True,
        start_sha: str | None = START_SHA,
        park_kind: str | None = "protected_path",
        worktree_path: str | None = WORKTREE,
        diff: str = UNIFIED,
    ) -> None:
        self.run = Run(
            id=new_id(),
            project_id=new_id(),
            repository_id=new_id(),
            template_name="epic",
            template_version=1,
            status="needs_you",
            budget_usd=Decimal("10"),
            inputs={"spec_folder": "specs/gates"},
            worktree_path=worktree_path,
            created_at=NOW,
            park_kind=park_kind,  # type: ignore[arg-type]
            park_path=BUILD,
            park_reason="protected path modified",
        )
        row = StepRun(
            id=new_id(),
            run_id=self.run.id,
            seq=1,
            path=BUILD,
            label=BUILD,
            kind="agent",
            gate="liveness",
            status="error",
        )
        attempt_repo = FakeAttemptRepository()
        if attempts:
            for n, sha in ((1, "aaaa"), (2, start_sha)):
                attempt_repo.add(
                    Attempt(
                        id=new_id(),
                        run_id=self.run.id,
                        step_run_id=row.id,
                        n=n,
                        status="done",
                        started_at=NOW,
                        start_sha=sha,
                    )
                )
        records = FakeGateRecordRepository()
        if park_kind is not None:
            records.add(
                GateRecord(
                    id=new_id(),
                    run_id=self.run.id,
                    at=NOW,
                    path=BUILD,
                    event=park_kind,  # type: ignore[arg-type]
                    actor="machine",
                    text="protected path modified",
                    payload=hits_payload(hits),
                )
            )
        self.git = FakeGit(diff=[diff])
        self.ports = RunFilesDiffPorts(
            runs=FakeRunRepository([self.run]),
            steps=FakeStepRunRepository([row]),
            attempts=attempt_repo,
            records=records,
            git=self.git,
        )


def test_a_recorded_hit_answers_its_unified_diff() -> None:
    world = World()

    answer = diff_run_file(world.ports, world.run.id, AGENTS)

    assert (answer.path, answer.from_sha, answer.diff) == (AGENTS, START_SHA, UNIFIED)


def test_the_diff_runs_from_the_latest_attempts_start_sha_inside_the_worktree() -> None:
    """The same range end AD-17 measured the hit from, so the two cannot disagree."""
    world = World()

    diff_run_file(world.ports, world.run.id, AGENTS)

    assert world.git.called("diff") == [(Path(WORKTREE), START_SHA, AGENTS)]


def test_a_hit_outside_the_spec_folder_is_answered_rather_than_refused() -> None:
    """The whole reason this mode has a scope of its own: every AD-17 anchor is outside it."""
    world = World()

    assert diff_run_file(world.ports, world.run.id, TEST_FILE).path == TEST_FILE


def test_a_path_that_is_not_one_of_the_hits_is_forbidden() -> None:
    world = World()

    with pytest.raises(Forbidden, match="not one of this run's protected paths"):
        diff_run_file(world.ports, world.run.id, "specs/gates/SPEC.md")


def test_an_escaping_path_is_invalid_before_the_hit_list_is_consulted() -> None:
    """`read_run_file`'s own order: `..` is a 422 whatever else would also refuse it."""
    world = World()

    with pytest.raises(Invalid, match="escapes the workspace"):
        diff_run_file(world.ports, world.run.id, "../etc/passwd")


def test_a_stop_that_recorded_no_hit_list_refuses_every_path() -> None:
    """A `blocked` park keeps no payload, so there is no file it is asking to be judged."""
    world = World(park_kind="blocked", hits=())

    with pytest.raises(Forbidden, match="not one of this run's protected paths"):
        diff_run_file(world.ports, world.run.id, AGENTS)


def test_an_unknown_run_is_not_found() -> None:
    world = World()

    with pytest.raises(NotFound, match="no run"):
        diff_run_file(world.ports, new_id(), AGENTS)


@pytest.mark.parametrize(
    "world",
    [World(attempts=False), World(start_sha=None), World(worktree_path=None)],
    ids=["no attempt", "no start sha", "no worktree"],
)
def test_a_park_with_nothing_to_diff_against_is_not_found(world: World) -> None:
    """A range needs both ends; the read says so rather than handing git an empty ref."""
    with pytest.raises(NotFound, match="no start commit"):
        diff_run_file(world.ports, world.run.id, AGENTS)


def test_a_park_on_a_row_the_plan_does_not_hold_is_not_found() -> None:
    world = World()
    world.ports.runs.update(world.run.model_copy(update={"park_path": "nowhere"}))

    with pytest.raises(NotFound, match="no start commit"):
        diff_run_file(world.ports, world.run.id, AGENTS)
