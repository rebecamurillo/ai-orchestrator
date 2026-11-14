"""Scope keys and the aggregator's missing rules (epic 2 story 4)."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.metrics.scopes import (
    Reading,
    can_call_model,
    count_over_scopes,
    repository_of,
    sum_over_scopes,
)
from orchestrator.application.metrics.values import value_at
from orchestrator.domain.entities.run_records import RunRepositoryRecord
from tests.unit.application.metrics_builders import (
    RUN_ID,
    make_ai,
    make_attempt,
    make_inputs,
    make_row,
)

LAST = 3


def reading(ai: object) -> Reading:
    return Decimal(1)


def test_scope_keys_follow_the_architecture() -> None:
    row = make_row("epics[0].stories[1].build", role="implement", story_id="s-1")
    ai = make_ai(row, make_attempt(row, 2), role="implement")
    values = sum_over_scopes(
        "x.y",
        "USD",
        make_inputs([row], [ai]),
        ("run", "epic", "story", "step", "attempt", "role", "model"),
        reading,
    )
    keys = {(v.scope_type, v.scope_key) for v in values}
    assert keys == {
        ("run", "run"),
        ("epic", "epics[0]"),
        ("story", "epics[0].stories[1]"),
        ("step", "epics[0].stories[1].build"),
        ("attempt", "epics[0].stories[1].build#2"),
        ("role", "implement"),
        ("model", "m"),
    }
    assert value_at(values, "x.y", "story", "epics[0].stories[1]").scope_label == "s-1"
    assert value_at(values, "x.y", "step", "epics[0].stories[1].build").scope_label == "build"


def test_role_and_model_are_set_only_where_the_scope_names_them() -> None:
    row = make_row("stories[0].build")
    values = sum_over_scopes(
        "x.y",
        "USD",
        make_inputs([row], [make_ai(row)]),
        ("run", "story", "attempt", "role", "model"),
        reading,
    )
    for v in values:
        if v.scope_type in ("run", "story"):
            assert (v.role, v.model) == (None, None)
    assert value_at(values, "x.y", "attempt", "stories[0].build#1").model == "m"
    assert value_at(values, "x.y", "role", "build").role == "build"
    assert value_at(values, "x.y", "model", "m").model == "m"


def test_can_call_model_by_kind_or_role() -> None:
    agent, shell = make_row(kind="agent"), make_row("s", kind="shell")
    assert can_call_model(make_ai(agent))
    assert not can_call_model(make_ai(shell))
    assert can_call_model(make_ai(shell, make_attempt(shell, role="consult")))
    assert can_call_model(make_ai(shell, make_attempt(shell, role="session")))


def test_all_reporting_is_a_plain_sum() -> None:
    row = make_row()
    ais = [make_ai(row, make_attempt(row, n)) for n in (1, 2)]
    run = value_at(
        sum_over_scopes("x.y", "n", make_inputs([row], ais), ("run",), reading), "x.y", "run", "run"
    )
    assert (run.value_num, run.missing) == (Decimal(2), None)


def test_some_reporting_is_partial_with_n_of_m() -> None:
    row = make_row()
    ais = [make_ai(row, make_attempt(row, n)) for n in (1, 2, 3)]
    measure = lambda ai: Decimal(1) if ai.attempt.n < LAST else "not available"  # noqa: E731
    run = value_at(
        sum_over_scopes("x.y", "n", make_inputs([row], ais), ("run",), measure), "x.y", "run", "run"
    )
    assert (run.value_num, run.missing, run.partial_n, run.partial_m) == (
        Decimal(2),
        "partial",
        2,
        3,
    )


def test_none_reporting_is_the_word_never_zero() -> None:
    row = make_row()
    ais = [make_ai(row, make_attempt(row, n)) for n in (1, 2)]
    same = value_at(
        sum_over_scopes("x.y", "n", make_inputs([row], ais), ("run",), lambda ai: "not recorded"),
        "x.y",
        "run",
        "run",
    )
    assert (same.value_num, same.missing) == (None, "not recorded")
    mixed = [make_ai(row, make_attempt(row, 1)), make_ai(row, make_attempt(row, 2))]
    words = {1: "not recorded", 2: "not available"}
    measure = lambda ai: words[ai.attempt.n]  # noqa: E731
    other = value_at(
        sum_over_scopes("x.y", "n", make_inputs([row], mixed), ("run",), measure),
        "x.y",
        "run",
        "run",
    )
    assert other.missing == "not available"


def test_a_shell_row_reads_no_model_called_with_or_without_an_attempt() -> None:
    shell = make_row("stories[0].verify", kind="shell")
    agent = make_row("stories[0].build", seq=2)
    skipped = make_row("stories[0].lint", seq=3, kind="shell")
    ais = [make_ai(shell), make_ai(agent)]
    values = sum_over_scopes(
        "x.y", "n", make_inputs([shell, agent, skipped], ais), ("run", "step", "attempt"), reading
    )
    for key in ("stories[0].verify", "stories[0].lint"):
        v = value_at(values, "x.y", "step", key)
        assert (v.missing, v.value_num) == ("n/a — shell step, no model called", None)
    assert (
        value_at(values, "x.y", "attempt", "stories[0].verify#1").missing
        == "n/a — shell step, no model called"
    )
    assert value_at(values, "x.y", "run", "run").value_num == Decimal(1)


def test_a_run_of_shell_rows_only_reads_no_model_called() -> None:
    shell = make_row(kind="shell")
    value = value_at(
        sum_over_scopes("x.y", "n", make_inputs([shell], []), ("run",), reading),
        "x.y",
        "run",
        "run",
    )
    assert value.missing == "n/a — shell step, no model called"


def test_an_agent_run_with_no_attempt_reads_not_recorded() -> None:
    value = value_at(
        sum_over_scopes("x.y", "n", make_inputs([make_row()], []), ("run",), reading),
        "x.y",
        "run",
        "run",
    )
    assert value.missing == "not recorded"


def test_no_story_frame_says_so_once() -> None:
    row = make_row("build")
    values = sum_over_scopes(
        "x.y", "n", make_inputs([row], [make_ai(row)]), ("run", "story"), reading
    )
    story = [v for v in values if v.scope_type == "story"]
    assert [(v.scope_key, v.missing) for v in story] == [("", "n/a — template has no story frame")]


def test_a_subset_with_nothing_selected_is_a_real_zero() -> None:
    row = make_row()
    values = sum_over_scopes(
        "x.y", "n", make_inputs([row], [make_ai(row)]), ("run",), reading, attempts=[]
    )
    assert value_at(values, "x.y", "run", "run").value_num == Decimal(0)


def test_by_model_splits_one_attempt_across_models() -> None:
    row = make_row()
    split = lambda ai: {"a": Decimal(1), "b": Decimal(2)}  # noqa: E731
    values = sum_over_scopes(
        "x.y",
        "n",
        make_inputs([row], [make_ai(row)]),
        ("model",),
        lambda ai: Decimal(3),
        by_model=split,
    )
    assert value_at(values, "x.y", "model", "a").value_num == Decimal(1)
    assert value_at(values, "x.y", "model", "b").value_num == Decimal(2)


def test_an_attempt_without_a_model_counts_under_unknown() -> None:
    row = make_row()
    ai = make_ai(row, make_attempt(row, model=None))
    values = sum_over_scopes("x.y", "n", make_inputs([row], [ai]), ("model",), reading)
    assert value_at(values, "x.y", "model", "unknown").value_num == Decimal(1)


def test_repository_is_the_workdir_when_a_run_repository_names_it() -> None:
    assert repository_of(make_row(with_resolved={"workdir": "repos/x"}), ["repos/x"]) == "repos/x"
    assert repository_of(make_row(with_resolved={"workdir": "other"}), ["repos/x"]) == "."
    assert repository_of(make_row(), []) == "."


def test_step_and_attempt_values_carry_the_repository() -> None:
    row = make_row(with_resolved={"workdir": "repos/x"})
    inputs = make_inputs([row], [make_ai(row)])
    inputs = type(inputs)(
        inputs.run,
        inputs.rows,
        inputs.attempts,
        inputs.records,
        inputs.now,
        (
            RunRepositoryRecord(
                id=RUN_ID,
                run_id=RUN_ID,
                path="repos/x",
                remote_url="u",
                base_branch="b",
                branch="b",
                base_tip="t",
            ),
        ),
    )
    values = sum_over_scopes("x.y", "n", inputs, ("step", "attempt"), reading)
    assert {v.repository for v in values} == {"repos/x"}


def test_count_over_scopes_counts_rows_and_attempts_and_keeps_run_zero() -> None:
    row = make_row("stories[0].build")
    inputs = make_inputs([row], [make_ai(row)])
    empty = count_over_scopes("c.d", inputs, ("run", "step"), [])
    assert [(v.scope_type, v.value_num) for v in empty] == [("run", Decimal(0))]
    counted = count_over_scopes(
        "c.d", inputs, ("run", "story", "step"), [(row, None), (row, make_ai(row))], source="k"
    )
    assert value_at(counted, "c.d", "run", "run", "k").value_num == Decimal(2)
    assert value_at(counted, "c.d", "step", "stories[0].build", "k").value_num == Decimal(2)
    only_steps = count_over_scopes("c.d", inputs, ("step",), [(row, None)])
    assert [v.scope_type for v in only_steps] == ["step"]


def test_a_session_on_a_shell_row_reads_its_own_figure_on_the_step() -> None:
    shell = make_row("verify", kind="shell")
    machine = make_ai(shell, make_attempt(shell, 1))
    session = make_ai(shell, make_attempt(shell, 2, role="session"))
    values = sum_over_scopes(
        "m", "u", make_inputs([shell], [machine, session]), ("step", "attempt"), reading
    )
    step = value_at(values, "m", "step", "verify")
    assert (step.value_num, step.missing) == (Decimal(1), None)
    assert (
        value_at(values, "m", "attempt", "verify#1").missing == "n/a — shell step, no model called"
    )
    alone = sum_over_scopes("m", "u", make_inputs([shell], [machine]), ("step", "attempt"), reading)
    assert value_at(alone, "m", "step", "verify").missing == "n/a — shell step, no model called"
