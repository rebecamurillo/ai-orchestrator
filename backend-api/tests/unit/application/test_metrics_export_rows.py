"""Export rows: one per stored value, in the column order of EXPERIENCE §5.10 (AC7, AC8)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.metrics.blind import HIDDEN
from orchestrator.application.metrics.export_rows import (
    EXPORT_COLUMNS,
    ExportSource,
    catalogue_for,
    to_export_row,
)
from orchestrator.application.use_cases.metrics_compare import export_rows
from orchestrator.domain.entities.metric_results import ResultVersion
from orchestrator.domain.ids import new_id
from tests.unit.application.test_metric_versions import PLAIN_ORIGIN, stored
from tests.unit.application.test_metrics_compare import World, role_value, run_value
from tests.unit.fakes.catalogue import catalogue_entry

HEADER = (
    "run_id,run_label,result_version,metric_id,method_id,scope_type,scope_key,scope_label,role,"
    "model,repository,attempt_n,source,value_num,unit,missing,carried_from,component_of,additive,"
    "calculated_at,entry_point,project_id,template_name,template_version,harness,origin_model,"
    "origin_repository,branch,commit,base_commit"
)


def a_version() -> ResultVersion:
    return ResultVersion(
        id=new_id(),
        run_id=new_id(),
        n=2,
        calculated_at=datetime(2026, 11, 13, 9, 5, 7, tzinfo=UTC),
        entry_point=("at_attempt_end", "workflow_step"),
        methods=(),
    )


def test_the_columns_are_exactly_the_documented_thirty_in_order() -> None:
    assert ",".join(EXPORT_COLUMNS) == HEADER
    assert len(EXPORT_COLUMNS) == 30  # noqa: PLR2004


def test_a_row_flattens_the_value_the_version_the_catalogue_and_the_origin() -> None:
    version, run_id = a_version(), new_id()
    entry = catalogue_entry(id="tokens.thinking", component_of="tokens.output", additive=True)
    value = stored(
        "tokens.thinking",
        scope_type="attempt",
        scope_key="a#1",
        scope_label="plan",
        role="plan",
        model="m",
        repository=".",
        attempt_n=1,
        source="harness",
        value_num=Decimal("12.50"),
        unit="count",
        carried_from=1,
    )

    row = to_export_row(ExportSource(run_id, "label", version, False), value, entry)

    assert row.run_id == str(run_id)
    assert (row.run_label, row.result_version, row.entry_point) == (
        "label",
        "2",
        "at_attempt_end+workflow_step",
    )
    assert row.calculated_at == "2026-11-13T09:05:07Z"
    assert (row.value_num, row.missing, row.carried_from) == ("12.50", "", "1")
    assert (row.component_of, row.additive) == ("tokens.output", "true")
    assert (row.attempt_n, row.model, row.scope_label) == ("1", "m", "plan")
    assert (row.template_name, row.template_version) == ("t", "1")
    assert (row.harness, row.origin_model, row.origin_repository) == ("claude", "m", ".")
    assert (row.branch, row.commit, row.base_commit) == ("b", "c", "base")


def test_a_missing_value_has_an_empty_figure_and_its_word_and_na_origins_read_as_words() -> None:
    origin = PLAIN_ORIGIN.model_copy(update={"harness": None, "harness_na": "spans_models"})
    value = stored("x.y", value_num=None, missing="not recorded", origin=origin)

    row = to_export_row(ExportSource(new_id(), "l", a_version(), True), value, None)

    assert (row.value_num, row.missing) == ("", "not recorded")
    assert row.harness == "n/a — spans_models"
    assert (row.component_of, row.additive, row.template_version) == ("", "", HIDDEN)


def test_the_catalogue_of_the_rows_lists_each_used_entry_once_in_order() -> None:
    entries = {
        e.id: e
        for e in (catalogue_entry(id="a.b"), catalogue_entry(id="c.d"), catalogue_entry(id="e.f"))
    }
    version = a_version()
    rows = [
        to_export_row(ExportSource(new_id(), "l", version, False), stored(metric), None)
        for metric in ("e.f", "a.b", "e.f", "unknown.metric")
    ]

    assert [e.id for e in catalogue_for(rows, entries)] == ["a.b", "e.f"]


def test_the_export_has_one_row_per_stored_value_of_every_run_at_its_version() -> None:
    world = World()
    a, b = world.run(label="A"), world.run(label="B")
    world.version(a, 1, [run_value("time.machine", "1")])
    world.version(
        a,
        2,
        [
            run_value("tokens.input", "2"),
            run_value("cost.gateway", "3"),
            run_value("zzz.unknown", "4"),
        ],
    )
    world.version(b, 1, [role_value("cost.gateway", "plan", "5")])

    result = export_rows(world.ports, world.query(a, b))

    assert [(r.run_label, r.metric_id, r.result_version) for r in result.rows] == [
        ("A", "cost.gateway", "2"),
        ("A", "tokens.input", "2"),
        ("A", "zzz.unknown", "2"),
        ("B", "cost.gateway", "1"),
    ]
    assert [e.id for e in result.catalogue] == ["cost.gateway", "tokens.input"]
    assert result.project_name == "familio"
    assert [h.run_id for h in result.runs] == [a.id, b.id]
    assert all(not any(ch.isalpha() for ch in r.value_num) for r in result.rows)


def test_a_run_without_a_version_adds_no_rows_and_blind_hides_labels_and_models() -> None:
    world = World()
    a, b = world.run(label="secret"), world.run(label="other")
    world.version(
        a,
        1,
        [
            stored(
                "tokens.input",
                scope_type="model",
                scope_key="opus-9",
                scope_label="opus-9",
                model="opus-9",
            )
        ],
    )
    export = export_rows(world.ports, world.query(a, b, blind=True))

    [row] = export.rows
    assert (row.run_label, row.model, row.scope_key, row.template_name, row.template_version) == (
        "R1",
        HIDDEN,
        HIDDEN,
        HIDDEN,
        HIDDEN,
    )
    assert "opus-9" not in repr(export) and "secret" not in repr(export)
    assert "initiative-hub" not in repr(export)
