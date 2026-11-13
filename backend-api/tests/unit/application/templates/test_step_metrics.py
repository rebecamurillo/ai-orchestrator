"""Template-level `metrics:` entries: step-produced results a template catalogues (epic 6 story 3).

The templates here are the test's own fixtures; the shipped `templates/*.yaml` are never read
(hard rule 6).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.application.templates.model import INVALID_VALUE
from orchestrator.application.templates.step_metric_model import (
    DUPLICATE_STEP_METRIC,
    INVALID_STEP_METRIC,
    INVALID_STEP_METRIC_FORMAT,
    INVALID_STEP_METRIC_ID,
    INVALID_STEP_METRIC_PATH,
)
from orchestrator.application.templates.step_metrics import declared_step_metrics
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.template import TemplateVersion
from tests.unit.fakes.runs import FakeRunRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

RUN_ID = UUID(int=7)
LINE_OF_FIRST_ENTRY = 4

HEAD = """name: bench-v1
version: 1
metrics:
"""
STEPS = """steps:
  - id: build
    run: make
    gate: deterministic
"""


def entry(
    metric_id: str = "step.bench-v1.heldout_tests",
    *,
    fmt: str | None = "junit",
    path: str | None = "out/heldout.xml",
    group: str | None = "step",
    drop: str | None = None,
) -> str:
    fields = {
        "id": metric_id,
        "label": "held-out tests",
        "group": group,
        "level": "A",
        "scopes": "[run]",
        "unit": "tests",
        "source": "the held-out suite",
        "additive": "false",
        "fingerprint_group": "false",
        "format": fmt,
        "path": path,
    }
    lines = [f"  - id: {metric_id}"]
    for key, value in fields.items():
        if key == "id" or value is None or key == drop:
            continue
        lines.append(f"    {key}: {value}")
    if drop != "missing_words":
        lines.append("    missing_words: []")
    if drop != "methods":
        lines.append("    methods:")
        lines.append("      - { n: 1, description: reads the report }")
    return "\n".join(lines) + "\n"


def template(*entries: str) -> str:
    return HEAD + "".join(entries) + STEPS


def check(text: str):  # type: ignore[no-untyped-def]
    return validate(text, templates=FakeTemplateVersionRepository([]))


def test_a_declared_entry_validates_and_is_parsed() -> None:
    result = check(template(entry()))

    assert result.errors == ()
    assert result.template is not None
    [metric] = result.template.metrics
    assert (metric.entry.id, metric.format, metric.path) == (
        "step.bench-v1.heldout_tests",
        "junit",
        "out/heldout.xml",
    )
    assert metric.entry.group == "step"
    assert metric.entry.scopes == ("run",)
    assert metric.line == LINE_OF_FIRST_ENTRY


def test_a_template_without_metrics_holds_none() -> None:
    result = check("name: bench-v1\nversion: 1\n" + STEPS)

    assert result.template is not None
    assert result.template.metrics == ()


@pytest.mark.parametrize("fmt", ["junit", "cobertura", "jacoco", "sarif"])
def test_each_of_the_four_formats_is_accepted(fmt: str) -> None:
    assert check(template(entry(fmt=fmt))).errors == ()


@pytest.mark.parametrize(
    ("kwargs", "reason", "key"),
    [
        ({"metric_id": "heldout_tests"}, INVALID_STEP_METRIC_ID, "id"),
        ({"metric_id": "step.other.heldout_tests"}, INVALID_STEP_METRIC_ID, "id"),
        ({"metric_id": "step.bench-v1.Held"}, INVALID_STEP_METRIC_ID, "id"),
        ({"fmt": "xml"}, INVALID_STEP_METRIC_FORMAT, "format"),
        ({"fmt": None}, INVALID_STEP_METRIC_FORMAT, None),
        ({"path": "/abs/out.xml"}, INVALID_STEP_METRIC_PATH, "path"),
        ({"path": "../out.xml"}, INVALID_STEP_METRIC_PATH, "path"),
        ({"path": "out/../x.xml"}, INVALID_STEP_METRIC_PATH, "path"),
        ({"path": "'out\\\\x.xml'"}, INVALID_STEP_METRIC_PATH, "path"),
        ({"path": "''"}, INVALID_STEP_METRIC_PATH, "path"),
        ({"path": None}, INVALID_STEP_METRIC_PATH, None),
        ({"group": "code"}, INVALID_STEP_METRIC, "group"),
        ({"drop": "label"}, f"{INVALID_STEP_METRIC}: missing field label", None),
    ],
)
def test_each_offence_is_one_error_at_its_line_with_a_reason(
    kwargs: dict[str, object], reason: str, key: str | None
) -> None:
    text = entry(**kwargs)  # type: ignore[arg-type]
    expected = LINE_OF_FIRST_ENTRY
    if key is not None:
        offset = next(
            i for i, line in enumerate(text.splitlines()) if line.lstrip(" -").startswith(f"{key}:")
        )
        expected += offset

    result = check(template(text))

    assert result.template is None
    assert [(e.line, e.reason) for e in result.errors] == [(expected, reason)]


def test_a_missing_methods_field_reports_both_catalogue_reasons() -> None:
    result = check(template(entry(drop="methods")))

    assert [(e.line, e.reason) for e in result.errors] == [
        (LINE_OF_FIRST_ENTRY, f"{INVALID_STEP_METRIC}: missing field methods"),
        (LINE_OF_FIRST_ENTRY, f"{INVALID_STEP_METRIC}: methods must be a non-empty list"),
    ]


def test_a_non_string_id_is_refused_without_raising() -> None:
    text = HEAD + "  - id: 5\n    label: x\n" + STEPS

    result = check(text)

    assert result.template is None
    assert (LINE_OF_FIRST_ENTRY, INVALID_STEP_METRIC_ID) in [
        (e.line, e.reason) for e in result.errors
    ]


def test_a_duplicate_id_is_refused_at_the_second_entry() -> None:
    first = entry()
    result = check(template(first, first))

    assert result.template is None
    assert [e.reason for e in result.errors] == [DUPLICATE_STEP_METRIC]
    assert result.errors[0].line == LINE_OF_FIRST_ENTRY + first.count("\n")


@pytest.mark.parametrize("value", ["metrics: 5", "metrics: [1]", "metrics: {a: b}"])
def test_metrics_that_is_not_a_list_of_mappings_is_invalid_value(value: str) -> None:
    result = check(f"name: bench-v1\nversion: 1\n{value}\n" + STEPS)

    assert result.template is None
    assert [(e.line, e.reason) for e in result.errors] == [(3, INVALID_VALUE)]


def test_an_invalid_template_name_skips_the_id_check() -> None:
    text = template(entry("step.Bad_Name.x")).replace("name: bench-v1", "name: Bad_Name")

    result = check(text)

    assert [e.reason for e in result.errors] == ["invalid slug"]


# --- declared_step_metrics ---------------------------------------------------------------------


def stored(text: str) -> TemplateVersion:
    return TemplateVersion(name="bench-v1", version=1, yaml=text, hash="h")


def a_run(version: int = 1) -> Run:
    return Run(
        id=RUN_ID,
        project_id=UUID(int=1),
        repository_id=UUID(int=2),
        template_name="bench-v1",
        template_version=version,
        status="done",
        budget_usd=Decimal("1"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def repositories(text: str | None, *, run: bool = True):  # type: ignore[no-untyped-def]
    runs = FakeRunRepository()
    if run:
        runs.add(a_run())
    templates = FakeTemplateVersionRepository([] if text is None else [stored(text)])
    return runs, templates


def test_the_runs_own_version_supplies_the_declared_entries() -> None:
    runs, templates = repositories(template(entry()))

    [metric] = declared_step_metrics(runs, templates, RUN_ID)

    assert metric.entry.id == "step.bench-v1.heldout_tests"


def test_a_missing_run_declares_nothing() -> None:
    runs, templates = repositories(template(entry()), run=False)

    assert declared_step_metrics(runs, templates, RUN_ID) == ()


def test_a_missing_version_declares_nothing() -> None:
    runs, templates = repositories(None)

    assert declared_step_metrics(runs, templates, RUN_ID) == ()


def test_a_stored_text_that_no_longer_validates_declares_nothing() -> None:
    runs, templates = repositories(template(entry(fmt="xml")))

    assert declared_step_metrics(runs, templates, RUN_ID) == ()
