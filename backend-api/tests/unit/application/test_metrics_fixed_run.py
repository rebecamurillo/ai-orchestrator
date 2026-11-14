"""Part A methods over the fixed Run (epic 2 story 4): every figure is a literal written here."""

from __future__ import annotations

from decimal import Decimal

import pytest

from orchestrator.application.metrics.live import live_values
from orchestrator.application.metrics.values import MetricValue, value_at
from tests.unit.application.metrics_fixed_run import RUN_ID, S0, S1, S2, FixedRun, build_fixed_run

D = Decimal


@pytest.fixture(scope="module")
def world() -> FixedRun:
    return build_fixed_run()


@pytest.fixture(scope="module")
def values(world: FixedRun) -> list[MetricValue]:
    return live_values(world.ports, RUN_ID)


def figure(
    values: list[MetricValue], metric: str, scope: str, key: str, source: str | None = None
) -> D | None:
    return value_at(values, metric, scope, key, source).value_num


@pytest.mark.parametrize(
    ("scope", "key", "gateway", "harness"),
    [
        ("run", "run", "22", "21.1"),
        ("epic", "epics[0]", "13", "13.7"),
        ("epic", "epics[1]", "9", "7.4"),
        ("story", S0, "6", "6.3"),
        ("story", S1, "7", "7.4"),
        ("story", S2, "9", "7.4"),
        ("role", "plan", "3", "3.3"),
        ("role", "implement", "15", "15.6"),
        ("role", "review", "2", "2.2"),
        ("model", "model-s", "5", "5.5"),
        ("model", "model-l", "17", "15.6"),
    ],
)
def test_money_totals_per_scope(
    values: list[MetricValue], scope: str, key: str, gateway: str, harness: str
) -> None:
    assert figure(values, "cost.gateway", scope, key) == D(gateway)
    assert figure(values, "cost.harness", scope, key) == D(harness)


def test_the_harness_total_is_partial_11_of_12(values: list[MetricValue]) -> None:
    total = value_at(values, "cost.harness", "run", "run")
    assert (total.missing, total.partial_n, total.partial_m) == ("partial", 11, 12)
    assert total.value_num == D("21.1")
    assert value_at(values, "cost.gateway", "run", "run").missing is None


def test_the_consult_attempt_has_no_harness_money(values: list[MetricValue]) -> None:
    senior = value_at(values, "cost.harness", "role", "senior")
    assert (senior.value_num, senior.missing) == (None, "not available")
    assert figure(values, "cost.gateway", "role", "senior") == D("2")


def test_output_and_cache_read_per_role(values: list[MetricValue]) -> None:
    assert figure(values, "tokens.output", "role", "plan") == D(300)
    assert figure(values, "tokens.output", "role", "implement") == D(1200)
    assert figure(values, "tokens.output", "role", "review") == D(100)
    assert figure(values, "tokens.output", "role", "senior") == D(10)
    assert figure(values, "tokens.cache_read", "role", "plan") == D(3000)
    assert figure(values, "tokens.cache_read", "role", "implement") == D(18000)
    assert figure(values, "tokens.cache_read", "run", "run") == D(22100)


def test_cache_hit_share(values: list[MetricValue]) -> None:
    share = figure(values, "tokens.cache_hit_share", "run", "run")
    assert share is not None
    assert round(share, 4) == D("0.9224")
    plan = figure(values, "tokens.cache_hit_share", "role", "plan")
    assert plan is not None
    assert round(plan, 4) == D("0.9009")


def test_role_and_model_are_set_only_on_role_model_and_attempt_values(
    values: list[MetricValue],
) -> None:
    for value in values:
        if value.scope_type in ("run", "epic", "story"):
            assert value.role is None, value
            assert value.model is None, value
    attempt = value_at(values, "cost.gateway", "attempt", f"{S0}.implement#2")
    assert (attempt.role, attempt.model, attempt.attempt_n) == ("implement", "model-l", 2)
    assert figure(values, "cost.gateway", "attempt", f"{S0}.implement#2") == D(3)


def test_the_three_retry_counts_are_one_each(values: list[MetricValue]) -> None:
    for kind in ("retry_auto", "redispatch", "operator"):
        assert figure(values, "process.retries", "run", "run", kind) == D(1)
    assert figure(values, "process.retries", "story", S0, "redispatch") == D(1)
    assert figure(values, "process.retries", "story", S1, "retry_auto") == D(1)
    assert figure(values, "process.retries", "story", S2, "operator") == D(1)


def test_of_which_cost_is_the_attempts_those_records_created(values: list[MetricValue]) -> None:
    # redispatch A3 (3 / 3.1), automatic retry A6 (3 / 3.1), operator retry A10 (3 / 3.1)
    for kind in ("retry_auto", "redispatch", "operator"):
        assert figure(values, "cost.retries", "run", "run", f"gateway:{kind}") == D(3)
        assert figure(values, "cost.retries", "run", "run", f"harness:{kind}") == D("3.1")
    assert figure(values, "cost.retries", "run", "run", "gateway") == D(9)
    assert figure(values, "cost.retries", "run", "run", "harness") == D("9.3")
    assert figure(values, "cost.retries", "epic", "epics[1]", "gateway") == D(3)


def test_failures_are_the_attempts_not_done(values: list[MetricValue]) -> None:
    assert figure(values, "process.failures", "run", "run") == D(2)
    assert figure(values, "cost.failures", "run", "run", "gateway") == D(4)
    assert figure(values, "cost.failures", "run", "run", "harness") == D("4.2")
    assert figure(values, "time.failures", "run", "run") == D(1200)


def test_waiting_on_you_and_machine_time(values: list[MetricValue]) -> None:
    assert figure(values, "time.parked", "run", "run") == D(1800)
    assert figure(values, "time.parked", "park", "4") == D(1800)
    assert value_at(values, "time.parked", "park", "4").scope_label == "blocked"
    assert figure(values, "time.wall", "run", "run") == D(9400)
    assert figure(values, "time.machine", "run", "run") == D(7600)
    assert figure(values, "time.wall", "epic", "epics[1]") == D(4900)
    assert figure(values, "time.machine", "epic", "epics[1]") == D(3100)
    assert figure(values, "time.machine", "epic", "epics[0]") == D(4400)
    assert figure(values, "time.operator_active", "run", "run") == D(900)
    assert figure(values, "time.attempt_seconds", "run", "run") == D(7200)
    assert figure(values, "time.attempt_seconds", "role", "implement") == D(3600)


def test_stories_done_and_cost_per_story_done(values: list[MetricValue]) -> None:
    assert figure(values, "process.stories_done", "run", "run", "done") == D(3)
    assert figure(values, "process.stories_done", "run", "run", "planned") == D(3)
    gateway = figure(values, "cost.per_story_done", "run", "run", "gateway")
    harness = value_at(values, "cost.per_story_done", "run", "run", "harness")
    assert gateway is not None
    assert round(gateway, 4) == D("7.3333")
    assert harness.value_num is not None
    assert round(harness.value_num, 4) == D("7.0333")
    assert (harness.missing, harness.partial_n, harness.partial_m) == ("partial", 11, 12)


def test_the_shell_row_says_no_model_was_called(values: list[MetricValue]) -> None:
    for metric in ("cost.gateway", "cost.harness", "tokens.output"):
        shell = value_at(values, metric, "step", f"{S0}.verify")
        assert shell.missing == "n/a — shell step, no model called"
        assert shell.value_num is None


def test_a_role_absent_from_the_template_reads_no_such_step(values: list[MetricValue]) -> None:
    absent = value_at(values, "cost.gateway", "role", "retro")
    assert absent.missing == "no such step in this template"
    assert absent.value_num is None


def test_parks_interventions_and_gates(values: list[MetricValue]) -> None:
    assert figure(values, "process.parks", "run", "run") == D(1)
    assert figure(values, "process.parks", "run", "run", "blocked") == D(1)
    assert figure(values, "process.interventions", "run", "run") == D(1)
    assert figure(values, "process.attempts", "run", "run") == D(12)
    assert figure(values, "process.attempts", "role", "implement") == D(6)
    assert value_at(values, "process.gate_first_pass", "run", "run").missing is not None


def test_the_budget_and_the_figure_gap(values: list[MetricValue]) -> None:
    assert figure(values, "budget.set", "run", "run") == D(50)
    assert figure(values, "budget.used", "run", "run") == D("0.462")
    assert value_at(values, "cost.figure_gap", "run", "run").missing == "not available"


WRITES = {"add", "add_many", "update", "mark_started", "mark_finished", "set_label"}


def test_live_values_writes_nothing(world: FixedRun) -> None:
    ports = world.ports
    watched = [ports.runs, ports.steps, ports.attempts, ports.records, ports.fact_sets]
    seen = [len(p.calls) for p in watched]  # type: ignore[attr-defined]
    stored = (len(world.records.records), len(world.gateway_reads.reads), len(world.fact_sets.sets))
    first = live_values(ports, RUN_ID)
    assert first == live_values(ports, RUN_ID)
    for port, count in zip(watched, seen, strict=True):
        made = [name for name, _ in port.calls[count:]]  # type: ignore[attr-defined]
        assert not WRITES & set(made)
    assert stored == (
        len(world.records.records),
        len(world.gateway_reads.reads),
        len(world.fact_sets.sets),
    )
