"""An unknown branch or base tip never fails a calculation (epic 2 retrospective X1, operator
order 2026-11-13): v1 is written, and only the origin fields that need the unknown value read
missing with a reason."""

from __future__ import annotations

from typing import Any

from orchestrator.application.metrics.versions import BASE_TIP_UNKNOWN, BRANCH_UNKNOWN
from orchestrator.application.use_cases.run_records import record_own_repository
from orchestrator.domain.entities.metric_results import StoredMetricValue
from orchestrator.domain.entities.run_records import ROOT_PATH, RunRepositoryRecord
from orchestrator.domain.ids import new_id
from orchestrator.domain.statuses import TERMINAL_RUN
from tests.unit.application.metrics_fixed_run import RUN_ID
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_calculate_metrics_job import Job, a_job, state_of
from tests.unit.application.test_run_repository_records_flow import created_run
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.run_records import FakeRunRepositoryRecords

HEAD = "head1"


def calculated_with(record: RunRepositoryRecord) -> tuple[Job, list[StoredMetricValue]]:
    """v1 of the fixed (ended) Run whose `.` repository is `record`."""
    job = a_job()
    assert job.fixed.run.status in TERMINAL_RUN
    job.ports.run_records.add(record.model_copy(update={"run_id": RUN_ID, "head_pushed": HEAD}))
    calculation_id = job.calculate()
    assert state_of(job, calculation_id).state == "done"
    [version] = job.versions.list_for_run(RUN_ID)
    assert version.n == 1
    stored = job.versions.values(version.id)
    assert stored
    return job, stored


def rooted(stored: list[StoredMetricValue]) -> list[StoredMetricValue]:
    found = [v for v in stored if v.origin.origin_repository == ROOT_PATH]
    assert found
    return found


def figures(stored: list[StoredMetricValue]) -> list[tuple[Any, ...]]:
    return sorted(
        (
            (
                (v.metric_id, v.scope_type, v.scope_key, v.source, v.role, v.model, v.attempt_n),
                (v.value_num, v.missing, v.partial_n, v.partial_m, v.unit),
            )
            for v in stored
        ),
        key=repr,
    )


def a_record(**fields: Any) -> RunRepositoryRecord:
    values: dict[str, Any] = {
        "id": new_id(),
        "run_id": RUN_ID,
        "path": ROOT_PATH,
        "remote_url": "u",
        "base_branch": "main",
        "branch": "feat/x",
        "base_tip": "base1",
    }
    return RunRepositoryRecord(**{**values, **fields})


def test_an_empty_branch_or_base_tip_is_built_and_loaded_as_unknown() -> None:
    record = a_record(branch="", base_tip="")
    assert (record.branch, record.base_tip) == (None, None)
    assert a_record().model_copy(update={"branch": None}).branch is None


def test_a_repo_init_run_without_a_branch_input_gets_v1_with_branch_unknown() -> None:
    records = FakeRunRepositoryRecords()
    run = created_run(records)
    assert "branch" not in run.inputs
    (own,) = records.rows
    assert own.branch is None

    _job, stored = calculated_with(own)

    for value in rooted(stored):
        assert (value.origin.branch, value.origin.branch_na) == (None, BRANCH_UNKNOWN)
        assert (value.origin.base_commit, value.origin.base_commit_na) == (fixtures.BASE_SHA, None)
        assert (value.origin.commit, value.origin.commit_na) == (HEAD, None)


def test_a_run_whose_base_tip_could_not_be_read_gets_v1_with_base_tip_unknown() -> None:
    run = created_run(FakeRunRepositoryRecords())
    unread = FakeRunRepositoryRecords()
    record_own_repository(unread, FakeGit(refs={}), run, "u", None)
    (own,) = unread.rows
    assert own.base_tip is None

    _job, stored = calculated_with(own.model_copy(update={"branch": "feat/x"}))

    for value in rooted(stored):
        assert (value.origin.base_commit, value.origin.base_commit_na) == (None, BASE_TIP_UNKNOWN)
        assert (value.origin.branch, value.origin.branch_na) == ("feat/x", None)


def test_known_facts_keep_their_origin_and_every_figure_is_unchanged_by_unknown_ones() -> None:
    _known_job, known = calculated_with(a_record())
    _unknown_job, unknown = calculated_with(a_record(branch="", base_tip=""))

    for value in rooted(known):
        assert (value.origin.branch, value.origin.branch_na) == ("feat/x", None)
        assert (value.origin.base_commit, value.origin.base_commit_na) == ("base1", None)
        assert (value.origin.commit, value.origin.commit_na) == (HEAD, None)
    assert figures(known) == figures(unknown)
