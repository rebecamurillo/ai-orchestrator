"""`carry_forward`, `origin_of` and `to_stored` (epic 2 story 5, ARCHITECTURE §5.6, RM-3)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.application.metrics.inputs import RunInputs
from orchestrator.application.metrics.values import NOT_AVAILABLE, NOT_RECORDED, MetricValue
from orchestrator.application.metrics.versions import carry_forward, origin_of, to_stored
from orchestrator.domain.entities.metric_results import Origin, StoredMetricValue
from orchestrator.domain.entities.run_records import RunRepositoryRecord
from orchestrator.domain.ids import new_id
from tests.unit.application.metrics_builders import (
    RUN_ID,
    make_ai,
    make_attempt,
    make_inputs,
    make_row,
)

PLAIN_ORIGIN = Origin(
    project_id=UUID(int=1),
    run_id=RUN_ID,
    template_name="t",
    template_version=1,
    harness="claude",
    origin_model="m",
    origin_repository=".",
    branch="b",
    commit="c",
    base_commit="base",
)


def stored(metric: str = "activity.tool_calls", **over: object) -> StoredMetricValue:
    fields: dict[str, object] = {
        "id": new_id(),
        "version_id": new_id(),
        "metric_id": metric,
        "method_id": f"{metric}@1",
        "scope_type": "attempt",
        "scope_key": "a#1",
        "value_num": Decimal(4),
        "unit": "count",
        "origin": PLAIN_ORIGIN,
    }
    return StoredMetricValue(**{**fields, **over})  # type: ignore[arg-type]


def missing(metric: str = "activity.tool_calls", **over: object) -> MetricValue:
    fields: dict[str, object] = {
        "metric_id": metric,
        "method_id": f"{metric}@2",
        "scope_type": "attempt",
        "scope_key": "a#1",
        "missing": NOT_RECORDED,
    }
    return MetricValue(**{**fields, **over})  # type: ignore[arg-type]


def test_a_not_recorded_value_takes_the_newest_earlier_figure_and_its_method() -> None:
    older = stored(value_num=Decimal(1), method_id="activity.tool_calls@1")
    newer = stored(value_num=Decimal(7), method_id="activity.tool_calls@1")

    [value] = carry_forward([missing()], [(2, [newer]), (1, [older])])

    assert (value.value_num, value.carried_from, value.method_id) == (
        Decimal(7),
        2,
        "activity.tool_calls@1",
    )
    assert value.missing is None
    assert value.unit == "count"


def test_a_partial_figure_is_carried_with_its_counts() -> None:
    earlier = stored(missing="partial", partial_n=1, partial_m=2)

    [value] = carry_forward([missing()], [(1, [earlier])])

    assert (value.missing, value.partial_n, value.partial_m) == ("partial", 1, 2)


def test_only_not_recorded_values_are_carried() -> None:
    present = MetricValue(
        "activity.tool_calls", "activity.tool_calls@2", "attempt", "a#1", value_num=Decimal(9)
    )
    other_word = missing(missing=NOT_AVAILABLE)

    assert carry_forward([present, other_word], [(1, [stored()])]) == [present, other_word]


@pytest.mark.parametrize(
    "different",
    [
        {"metric_id": "activity.files_read"},
        {"scope_type": "step"},
        {"scope_key": "a#2"},
        {"source": "gateway"},
        {"role": "build"},
        {"model": "other"},
    ],
)
def test_a_figure_with_another_key_is_not_carried(different: dict[str, str]) -> None:
    value = missing()

    assert carry_forward([value], [(1, [stored(**different)])]) == [value]


def test_an_earlier_value_without_a_figure_is_not_carried() -> None:
    word = stored(value_num=None, missing=NOT_RECORDED)
    value = missing()

    assert carry_forward([value], [(1, [word])]) == [value]
    assert carry_forward([value], []) == [value]


def one_row_inputs(**record_over: object) -> tuple[RunInputs, MetricValue]:
    row = make_row("build")
    attempt = make_attempt(row, harness="claude", model="m")
    record = RunRepositoryRecord(
        id=new_id(),
        run_id=RUN_ID,
        path=".",
        remote_url="u",
        base_branch="main",
        branch="feat/x",
        base_tip="base1",
        head_pushed="pushed1",
        **record_over,  # type: ignore[arg-type]
    )
    inputs = replace(make_inputs([row], [make_ai(row, attempt)]), run_repositories=[record])
    return inputs, MetricValue("cost.total", "cost.total@1", "run", "run")


def test_a_run_scope_with_one_harness_model_and_repository_has_a_full_origin() -> None:
    inputs, value = one_row_inputs()

    origin = origin_of(value, inputs)

    assert (origin.harness, origin.origin_model, origin.origin_repository) == ("claude", "m", ".")
    assert (origin.branch, origin.commit, origin.base_commit) == ("feat/x", "pushed1", "base1")
    assert origin.run_id == inputs.run.id
    assert origin.template_name == inputs.run.template_name


def test_the_local_head_stands_in_when_nothing_was_pushed() -> None:
    inputs, value = one_row_inputs()
    record = inputs.run_repositories[0].model_copy(
        update={"head_pushed": None, "head_local_at_end": "local1"}
    )

    origin = origin_of(value, replace(inputs, run_repositories=[record]))

    assert origin.commit == "local1"


def test_a_repository_with_neither_head_says_the_commit_is_missing() -> None:
    inputs, value = one_row_inputs()
    record = inputs.run_repositories[0].model_copy(update={"head_pushed": None})

    origin = origin_of(value, replace(inputs, run_repositories=[record]))

    assert (origin.commit, origin.commit_na) == (None, "commit_missing")
    assert origin.branch == "feat/x"


def test_no_repository_row_says_so_for_branch_and_commits() -> None:
    inputs, value = one_row_inputs()

    origin = origin_of(value, replace(inputs, run_repositories=[]))

    assert origin.origin_repository == "."
    assert {origin.branch_na, origin.commit_na, origin.base_commit_na} == {"no_repository_record"}


def test_a_scope_that_spans_harnesses_models_and_repositories_says_so() -> None:
    rows = [make_row("a", 1, with_resolved={"workdir": "sub"}), make_row("b", 2)]
    attempts = [
        make_ai(rows[0], make_attempt(rows[0], harness="claude", model="m1")),
        make_ai(rows[1], make_attempt(rows[1], harness="codex", model="m2")),
    ]
    inputs, _ = one_row_inputs()
    sub = inputs.run_repositories[0].model_copy(update={"id": new_id(), "path": "sub"})
    inputs = replace(
        make_inputs(rows, attempts), run_repositories=[inputs.run_repositories[0], sub]
    )

    origin = origin_of(MetricValue("cost.total", "cost.total@1", "run", "run"), inputs)

    assert origin.harness_na == "spans_harnesses"
    assert origin.origin_model_na == "spans_models"
    assert origin.origin_repository_na == "spans_repositories"
    assert origin.branch_na == origin.commit_na == origin.base_commit_na == "spans_repositories"


def test_a_value_names_its_own_model_and_repository() -> None:
    inputs, _ = one_row_inputs()
    value = MetricValue(
        "cost.total", "cost.total@1", "model", "other", model="other", repository="."
    )

    origin = origin_of(value, inputs)

    assert origin.origin_model == "other"
    assert origin.harness_na == "no_model_called"
    assert origin.origin_repository == "."
    assert origin.branch == "feat/x"


def test_a_shell_only_scope_calls_no_model() -> None:
    row = make_row("sh", kind="shell")
    inputs = make_inputs([row], [make_ai(row, make_attempt(row, harness=None, model=None))])

    origin = origin_of(MetricValue("time.active", "time.active@1", "step", "sh"), inputs)

    assert origin.harness_na == "no_model_called"
    assert origin.origin_model_na == "no_model_called"
    assert origin.origin_repository == "."


def test_a_scope_without_attempts_has_no_repository_scope() -> None:
    inputs, _ = one_row_inputs()

    origin = origin_of(MetricValue("x.y", "x.y@1", "step", "nope"), inputs)

    assert origin.origin_repository_na == "no_repository_scope"
    assert origin.branch_na == "no_repository_scope"


@pytest.mark.parametrize(
    ("scope_type", "key"),
    [
        ("gate", "build"),
        ("model", "m"),
        ("step", "build"),
        ("attempt", "build#1"),
        ("tool", "Bash"),
    ],
)
def test_each_scope_type_finds_its_attempts(scope_type: str, key: str) -> None:
    inputs, _ = one_row_inputs()

    origin = origin_of(MetricValue("x.y", "x.y@1", scope_type, key), inputs)

    assert origin.harness == "claude"


def test_to_stored_copies_every_field_and_gets_its_own_id() -> None:
    value = MetricValue(
        "cost.total",
        "cost.total@1",
        "attempt",
        "a#1",
        scope_label="a",
        role="build",
        model="m",
        repository=".",
        attempt_n=1,
        source="gateway",
        value_num=Decimal("1.5"),
        unit="usd",
        carried_from=1,
    )
    version_id = new_id()

    result = to_stored(value, version_id, PLAIN_ORIGIN)

    assert result.version_id == version_id
    assert result.value_num == Decimal("1.5")
    assert (result.role, result.model, result.attempt_n, result.carried_from) == (
        "build",
        "m",
        1,
        1,
    )
    assert result.origin is PLAIN_ORIGIN
    assert result.id != to_stored(value, version_id, PLAIN_ORIGIN).id


def test_a_stored_value_refuses_a_figure_and_a_word_together_except_partial() -> None:
    with pytest.raises(ValueError, match="both set"):
        stored(missing=NOT_RECORDED)
    assert stored(missing="partial").missing == "partial"


def test_an_origin_field_is_a_value_or_a_reason_never_both_or_neither() -> None:
    fields = PLAIN_ORIGIN.model_dump()
    with pytest.raises(ValueError, match="exactly one"):
        Origin(**{**fields, "harness_na": "x"})
    with pytest.raises(ValueError, match="exactly one"):
        Origin(**{**fields, "harness": None})
