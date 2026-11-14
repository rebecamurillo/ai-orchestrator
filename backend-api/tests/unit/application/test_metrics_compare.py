"""The comparison of selected Runs (epic 4 story 1: AC1-AC6, AC8, AC10)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from orchestrator.application.metrics.blind import HIDDEN
from orchestrator.application.metrics.compare_views import Comparison
from orchestrator.application.use_cases.metrics_compare import (
    CompareQuery,
    MetricsComparePorts,
    compare_runs,
    parse_runs,
    parse_versions,
)
from orchestrator.domain.entities.metric_results import ResultVersion, StoredMetricValue
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.run_records import RunRepositoryRecord
from orchestrator.domain.errors import Invalid, NotFound
from orchestrator.domain.ids import new_id
from tests.unit.application.metrics_builders import make_row
from tests.unit.application.test_metric_versions import stored
from tests.unit.application.test_metrics_spend import a_project, a_run, a_set
from tests.unit.fakes.catalogue import FakeCatalogue, catalogue_entry
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.facts import FakeFactSetRepository
from tests.unit.fakes.metric_results import FakeResultVersionRepository
from tests.unit.fakes.projects import FakeProjectRepository
from tests.unit.fakes.run_records import FakeRunRepositoryRecords
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
ENTRIES = (
    catalogue_entry(id="cost.gateway", scopes=("run", "role"), additive="within_scope_type"),
    catalogue_entry(id="cost.harness", scopes=("run", "role"), additive="within_scope_type"),
    catalogue_entry(id="time.machine", scopes=("run",), additive=False),
    catalogue_entry(id="process.stories_done", scopes=("run",), additive=False),
    catalogue_entry(id="tokens.input", scopes=("run",), additive=False),
)


class World:
    def __init__(self) -> None:
        self.project = a_project("familio")
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.versions = FakeResultVersionRepository()
        self.fact_sets = FakeFactSetRepository()
        self.records = FakeRunRepositoryRecords()
        self.projects = FakeProjectRepository([self.project])
        self.ports = MetricsComparePorts(
            projects=self.projects,
            runs=self.runs,
            steps=self.steps,
            versions=self.versions,
            fact_sets=self.fact_sets,
            run_records=self.records,
            catalogue=FakeCatalogue(ENTRIES),
            clock=FakeClock(NOW),
        )

    def run(self, **over: Any) -> Run:
        run = a_run(self.project, **over)
        self.runs.add(run)
        return run

    def version(self, run: Run, n: int, values: list[StoredMetricValue]) -> ResultVersion:
        version = ResultVersion(
            id=new_id(), run_id=run.id, n=n, calculated_at=NOW, entry_point=("manual",), methods=()
        )
        self.versions.add(version, values)
        return version

    def query(
        self, *runs: Run, v: dict[UUID, int] | None = None, blind: bool = False
    ) -> CompareQuery:
        return CompareQuery(tuple(r.id for r in runs), v or {}, blind)


def run_value(metric: str, figure: str, **over: Any) -> StoredMetricValue:
    return stored(
        metric,
        scope_type="run",
        scope_key="run",
        value_num=Decimal(figure),
        unit="USD",
        **over,
    )


def test_parse_runs_and_versions() -> None:
    a, b = new_id(), new_id()

    assert parse_runs(f"{a},{b},") == (a, b)
    assert parse_versions(f"{a}:1,{b}:2") == {a: 1, b: 2}
    assert parse_versions("") == {}


@pytest.mark.parametrize("text", ["nope", f"{new_id()}"])
def test_a_bad_version_token_is_invalid(text: str) -> None:
    with pytest.raises(Invalid):
        parse_versions(text)


def test_a_bad_run_id_is_invalid() -> None:
    with pytest.raises(Invalid):
        parse_runs("not-a-uuid")


def test_fewer_than_two_distinct_runs_is_invalid() -> None:
    world = World()
    run = world.run()

    with pytest.raises(Invalid):
        compare_runs(world.ports, world.query(run))
    with pytest.raises(Invalid):
        compare_runs(world.ports, world.query(run, run))


def test_an_unknown_run_is_not_found() -> None:
    world = World()
    run = world.run()

    with pytest.raises(NotFound):
        compare_runs(world.ports, CompareQuery((run.id, new_id()), {}, False))


def test_runs_of_two_projects_are_invalid() -> None:
    world = World()
    other = a_project("orchestrator")
    world.projects.add(other)
    first = world.run()
    second = a_run(other)
    world.runs.add(second)

    with pytest.raises(Invalid, match="more than one project"):
        compare_runs(world.ports, world.query(first, second))


def test_a_version_the_run_lacks_is_not_found_and_a_stray_v_is_invalid() -> None:
    world = World()
    first, second = world.run(), world.run()
    world.version(first, 1, [])

    with pytest.raises(NotFound):
        compare_runs(world.ports, world.query(first, second, v={first.id: 2}))
    with pytest.raises(Invalid):
        compare_runs(world.ports, world.query(first, second, v={new_id(): 1}))


def test_the_answer_is_plain_comparison_data() -> None:
    world = World()
    a, b = world.run(), world.run()

    assert isinstance(compare_runs(world.ports, world.query(a, b)), Comparison)


def test_each_column_holds_its_selected_version_and_the_latest_by_default() -> None:
    world = World()
    a, b = world.run(), world.run()
    world.version(a, 1, [run_value("time.machine", "10")])
    world.version(a, 2, [run_value("time.machine", "20", method_id="time.machine@1")])
    world.version(b, 1, [run_value("time.machine", "30")])

    pinned = compare_runs(world.ports, world.query(a, b, v={a.id: 1}))
    latest = compare_runs(world.ports, world.query(a, b))

    [metric] = pinned.metrics
    assert metric.cells[a.id][0].value_num == "10"
    assert [pinned.runs[0].selected_version, pinned.runs[0].versions_available] == [1, [1, 2]]
    assert latest.metrics[0].cells[a.id][0].value_num == "20"
    assert latest.runs[0].selected_version == 2  # noqa: PLR2004
    assert latest.runs[1].selected_version == 1


def test_a_run_without_a_version_has_an_empty_column() -> None:
    world = World()
    a, b = world.run(), world.run()
    world.version(a, 1, [run_value("time.machine", "10")])

    result = compare_runs(world.ports, world.query(a, b))

    assert result.runs[1].selected_version is None
    assert result.runs[1].versions_available == []
    assert result.metrics[0].cells[b.id] == []
    assert result.metrics[0].methods[b.id] == []


def test_different_methods_are_flagged_and_listed_per_run() -> None:
    world = World()
    a, b = world.run(), world.run()
    world.version(a, 1, [run_value("time.machine", "10", method_id="time.machine@1")])
    world.version(b, 1, [run_value("time.machine", "12", method_id="time.machine@2")])

    [metric] = compare_runs(world.ports, world.query(a, b)).metrics

    assert metric.methods_differ is True
    assert metric.methods == {a.id: ["time.machine@1"], b.id: ["time.machine@2"]}


def test_equal_methods_do_not_differ_and_a_run_without_the_metric_is_not_a_difference() -> None:
    world = World()
    a, b, c = world.run(), world.run(), world.run()
    world.version(a, 1, [run_value("time.machine", "10")])
    world.version(b, 1, [run_value("time.machine", "12")])
    world.version(c, 1, [run_value("tokens.input", "1")])

    metrics = {m.metric_id: m for m in compare_runs(world.ports, world.query(a, b, c)).metrics}

    assert metrics["time.machine"].methods_differ is False
    assert metrics["tokens.input"].methods_differ is False


def test_metrics_follow_the_catalogue_and_skip_those_without_a_value() -> None:
    world = World()
    a, b = world.run(), world.run()
    world.version(a, 1, [run_value("tokens.input", "1"), run_value("cost.gateway", "2")])
    world.version(b, 1, [])

    result = compare_runs(world.ports, world.query(a, b))

    assert [m.metric_id for m in result.metrics] == ["cost.gateway", "tokens.input"]
    assert result.diff_size == {a.id: "not run", b.id: "not run"}
    assert result.project_name == "familio"


def role_value(metric: str, role: str, figure: str) -> StoredMetricValue:
    return stored(
        metric,
        scope_type="role",
        scope_key=role,
        role=role,
        value_num=Decimal(figure),
        unit="USD",
    )


def test_story_work_carries_both_runs_sums_and_the_structure_flag() -> None:
    world = World()
    a, b = world.run(), world.run()
    world.version(
        a,
        1,
        [
            role_value("cost.gateway", r, f)
            for r, f in (("plan", "1"), ("implement", "2"), ("review", "3"))
        ],
    )
    world.version(b, 1, [role_value("cost.gateway", "orchestrate", "5")])
    world.steps.add_many(
        [make_row("epics[0].stories[0].orchestrate", run_id=b.id, role="orchestrate")]
    )

    [metric] = compare_runs(world.ports, world.query(a, b)).metrics
    [family] = metric.families

    assert family.family == "story work"
    assert family.step_structure_differs is True
    assert (family.cells[a.id].value_num, family.cells[a.id].roles) == (
        "6",
        ["plan", "implement", "review"],
    )
    assert (family.cells[b.id].value_num, family.cells[b.id].roles) == ("5", ["orchestrate"])


def test_orchestrate_outside_a_story_frame_reads_no_such_step() -> None:
    world = World()
    a, b = world.run(), world.run()
    world.version(a, 1, [role_value("cost.gateway", "plan", "1")])
    world.version(b, 1, [role_value("cost.gateway", "orchestrate", "5")])
    world.steps.add_many([make_row("orchestrate", run_id=b.id, role="orchestrate")])

    [metric] = compare_runs(world.ports, world.query(a, b)).metrics
    [family] = metric.families

    assert family.cells[b.id].missing == "no such step in this template"
    assert family.cells[b.id].value_num is None


def test_metrics_that_are_not_role_additive_have_no_families() -> None:
    world = World()
    a, b = world.run(), world.run()
    world.version(a, 1, [role_value("time.machine", "plan", "1")])
    world.version(b, 1, [role_value("time.machine", "plan", "1")])

    [metric] = compare_runs(world.ports, world.query(a, b)).metrics

    assert metric.families == []


def test_the_same_work_row_flags_a_differing_base_commit() -> None:
    world = World()
    a, b = (
        world.run(inputs={"initiative_folder": "initiatives/x"}),
        world.run(inputs={"initiative_folder": "initiatives/x"}),
    )
    for run, tip in ((a, "aaa"), (b, "bbb")):
        world.records.rows.append(
            RunRepositoryRecord(
                id=new_id(),
                run_id=run.id,
                path=".",
                remote_url="u",
                base_branch="main",
                base_tip=tip,
            )
        )

    same = compare_runs(world.ports, world.query(a, b)).same_work

    assert same.differs is True
    assert same.runs[a.id].base_commits == {".": "aaa"}
    assert same.runs[b.id].base_commits == {".": "bbb"}
    assert same.runs[a.id].initiative_folder == "initiatives/x"


def test_the_same_work_row_flags_initiative_and_stories_planned_and_otherwise_agrees() -> None:
    world = World()
    a = world.run(inputs={"spec_folder": "specs/a"})
    b = world.run(inputs={"spec_folder": "specs/b"})
    c = world.run(inputs={"spec_folder": "specs/a"})
    d = world.run(inputs={"spec_folder": "specs/a"})
    for run, planned in ((a, "4"), (b, "4"), (c, "5"), (d, "4")):
        world.version(
            run,
            1,
            [
                stored(
                    "process.stories_done",
                    scope_type="run",
                    scope_key="run",
                    source="done",
                    value_num=Decimal(1),
                ),
                stored(
                    "process.stories_done",
                    scope_type="run",
                    scope_key="run",
                    source="planned",
                    value_num=Decimal(planned),
                ),
            ],
        )

    assert compare_runs(world.ports, world.query(a, b)).same_work.differs is True
    assert compare_runs(world.ports, world.query(a, c)).same_work.differs is True
    same = compare_runs(world.ports, world.query(a, d)).same_work
    assert same.differs is False
    assert same.runs[a.id].stories_planned == 4  # noqa: PLR2004


def test_the_header_reads_stories_done_harness_branch_and_the_models_by_role() -> None:
    world = World()
    a, b = world.run(label=""), world.run(label="mine", label_set_by_operator=True)
    world.version(
        a,
        1,
        [
            stored(
                "process.stories_done",
                scope_type="run",
                scope_key="run",
                source="done",
                value_num=Decimal(3),
            ),
            stored(
                "process.stories_done",
                scope_type="run",
                scope_key="run",
                source="planned",
                value_num=Decimal(4),
            ),
            stored(
                "tokens.input", scope_type="attempt", scope_key="p#1", role="plan", model="opus"
            ),
            stored(
                "tokens.input", scope_type="attempt", scope_key="p#2", role="plan", model="sonnet"
            ),
            stored("tokens.input", scope_type="attempt", scope_key="p#3", role=None, model="x"),
            stored(
                "tokens.input", scope_type="attempt", scope_key="p#4", role="review", model=None
            ),
        ],
    )
    world.version(
        b,
        1,
        [
            stored(
                "process.stories_done",
                scope_type="run",
                scope_key="run",
                source="done",
                value_num=Decimal(3),
            )
        ],
    )
    world.fact_sets.sets.append(a_set(a, True))

    first, second = compare_runs(world.ports, world.query(a, b)).runs

    assert (first.label, first.short_id) == ("R1", a.id.hex[:8])
    assert second.label == "mine" and second.label_set_by_operator is True
    assert (first.stories_done.done, first.stories_done.planned) == (3, 4)  # type: ignore[union-attr]
    assert second.stories_done is None
    assert first.models_by_role == {"plan": ["opus", "sonnet"]}
    assert (first.harness, first.base_branch, first.status) == ("claude", "main", "done")
    assert (first.template_name, first.template_version) == ("initiative-hub", "3")
    assert (first.subscription, second.subscription) == (True, None)


def test_the_harness_figure_carries_its_difference_from_the_gateway() -> None:
    world = World()
    a, b, c = world.run(), world.run(), world.run()
    world.version(a, 1, [run_value("cost.gateway", "15.35"), run_value("cost.harness", "16.01")])
    world.version(b, 1, [run_value("cost.gateway", "10"), run_value("cost.harness", "9.88")])
    world.version(c, 1, [run_value("cost.harness", "5")])

    metrics = {m.metric_id: m for m in compare_runs(world.ports, world.query(a, b, c)).metrics}

    assert metrics["cost.harness"].harness_delta == {
        a.id: "+$0.66 vs gateway",
        b.id: "-$0.12 vs gateway",
    }
    assert metrics["cost.gateway"].harness_delta == {}


def test_equal_figures_read_plus_minus_zero() -> None:
    world = World()
    a, b = world.run(), world.run()
    world.version(a, 1, [run_value("cost.gateway", "4"), run_value("cost.harness", "4.001")])
    world.version(b, 1, [run_value("cost.harness", "4")])

    [_, harness] = compare_runs(world.ports, world.query(a, b)).metrics

    assert harness.harness_delta == {a.id: "±$0.00 vs gateway"}


def test_a_figure_that_is_a_word_carries_no_delta() -> None:
    world = World()
    a, b = world.run(), world.run()
    missing = stored(
        "cost.gateway", scope_type="run", scope_key="run", value_num=None, missing="not recorded"
    )
    world.version(a, 1, [missing, run_value("cost.harness", "4")])
    world.version(b, 1, [run_value("cost.harness", "4")])

    metrics = {m.metric_id: m for m in compare_runs(world.ports, world.query(a, b)).metrics}

    assert metrics["cost.harness"].harness_delta == {}
    assert metrics["cost.gateway"].cells[a.id][0].value_num is None
    assert metrics["cost.gateway"].cells[a.id][0].missing == "not recorded"


def test_blind_replaces_labels_template_and_models_and_keeps_the_rest() -> None:
    world = World()
    a, b = world.run(label="secret label A"), world.run(label="secret label B")
    model_scope = stored(
        "tokens.input",
        scope_type="model",
        scope_key="claude-opus-5",
        scope_label="claude-opus-5",
        model="claude-opus-5",
    )
    attempt = stored(
        "tokens.input", scope_type="attempt", scope_key="p#1", role="plan", model="claude-opus-5"
    )
    for run in (a, b):
        world.version(run, 1, [model_scope, attempt])

    result = compare_runs(world.ports, world.query(a, b, blind=True))
    text = repr(result)

    assert [h.label for h in result.runs] == ["R1", "R2"]
    assert all(h.template_name == HIDDEN == h.template_version for h in result.runs)
    assert result.runs[0].models_by_role == {"plan": [HIDDEN]}
    for secret in ("secret label", "initiative-hub", "claude-opus-5"):
        assert secret not in text
    assert result.runs[0].harness == "claude" and result.runs[0].status == "done"
    assert str(a.id) in text
