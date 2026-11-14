"""The template-level `metrics:` list: step-produced results a Template catalogues (AD-15).

Pure: no I/O. An entry is a catalogue entry (the schema of the shipped catalogue, checked by the
same function) plus the `format` of the report a step writes and the repository-relative `path`
glob it writes it at. Its id is `step.{template name}.{name}`, so one template cannot catalogue a
metric under another's name.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, cast, get_args
from uuid import UUID

from orchestrator.application.metrics.catalogue import build_entry, check_entry_fields
from orchestrator.application.templates.lines import LinedMap, as_map, as_seq, key_line, line_of
from orchestrator.application.templates.model import INVALID_VALUE, ValidationError
from orchestrator.application.templates.step_metric_model import (
    DUPLICATE_STEP_METRIC,
    INVALID_STEP_METRIC,
    INVALID_STEP_METRIC_FORMAT,
    INVALID_STEP_METRIC_ID,
    INVALID_STEP_METRIC_PATH,
    StepMetric,
    StepMetricFormat,
)
from orchestrator.application.templates.table import METRICS_KEY, NAME_KEY, is_slug, problem
from orchestrator.domain.ports.repositories import RunRepository
from orchestrator.domain.ports.templates import TemplateVersionRepository

FORMAT_KEY = "format"
PATH_KEY = "path"
STEP_GROUP = "step"
FORMATS: tuple[str, ...] = get_args(StepMetricFormat)
_NAME = "[a-z][a-z0-9_]*"


def _entries(root: LinedMap) -> list[LinedMap] | None:
    entries = as_seq(root.get(METRICS_KEY))
    if entries is None:
        return None
    return [mapping for mapping in (as_map(item) for item in entries) if mapping is not None]


def _id_ok(entry: LinedMap, template: object) -> bool:
    if not is_slug(template):
        return True
    pattern = rf"^step\.{re.escape(str(template))}\.{_NAME}$"
    return isinstance(entry.get("id"), str) and re.match(pattern, entry["id"]) is not None


def _path_ok(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not value.startswith("/")
        and "\\" not in value
        and ".." not in value.split("/")
    )


def _check_entry(entry: LinedMap, template: object) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not _id_ok(entry, template):
        errors.append(problem(key_line(entry, "id", entry.line), INVALID_STEP_METRIC_ID))
    if entry.get(FORMAT_KEY) not in FORMATS:
        errors.append(problem(key_line(entry, FORMAT_KEY, entry.line), INVALID_STEP_METRIC_FORMAT))
    if not _path_ok(entry.get(PATH_KEY)):
        errors.append(problem(key_line(entry, PATH_KEY, entry.line), INVALID_STEP_METRIC_PATH))
    if entry.get("group") != STEP_GROUP:
        errors.append(problem(key_line(entry, "group", entry.line), INVALID_STEP_METRIC))
    own = {k: v for k, v in entry.items() if k not in (FORMAT_KEY, PATH_KEY)}
    for reason in check_entry_fields(own):
        errors.append(problem(entry.line, f"{INVALID_STEP_METRIC}: {reason}"))
    return errors


def check_metrics(root: LinedMap) -> list[ValidationError]:
    """Every offence of the `metrics:` key, each at a real line; never raises."""
    if METRICS_KEY not in root:
        return []
    line = key_line(root, METRICS_KEY, root.line)
    seq = as_seq(root[METRICS_KEY])
    if seq is None:
        return [problem(line, INVALID_VALUE)]
    errors: list[ValidationError] = []
    seen: set[str] = set()
    for item in seq:
        entry = as_map(item)
        if entry is None:
            errors.append(problem(line_of(item, seq.line), INVALID_VALUE))
            continue
        errors += _check_entry(entry, root.get(NAME_KEY))
        metric_id = entry.get("id")
        if isinstance(metric_id, str) and metric_id in seen:
            errors.append(problem(key_line(entry, "id", entry.line), DUPLICATE_STEP_METRIC))
        if isinstance(metric_id, str):
            seen.add(metric_id)
    return errors


def parse_metrics(root: LinedMap) -> tuple[StepMetric, ...]:
    """The entries of a file `check_metrics` accepted."""
    return tuple(
        StepMetric(
            line=entry.line,
            entry=build_entry(_catalogue_fields(entry)),
            format=cast("StepMetricFormat", entry[FORMAT_KEY]),
            path=entry[PATH_KEY],
        )
        for entry in _entries(root) or []
    )


def _catalogue_fields(entry: LinedMap) -> Mapping[str, Any]:
    return {k: _plain(v) for k, v in entry.items() if k not in (FORMAT_KEY, PATH_KEY)}


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _plain(sub) for key, sub in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def declared_step_metrics(
    runs: RunRepository, templates: TemplateVersionRepository, run_id: UUID
) -> tuple[StepMetric, ...]:
    """What the Run's own template version declared; `()` when it cannot be read.

    A stored version validated once; a later failure to read it is not raised from here.
    """
    # Imported here: `validate` reaches this module through `keys`, so a top-level import cycles.
    from orchestrator.application.templates.validate import validate  # noqa: PLC0415

    run = runs.get(run_id)
    if run is None:
        return ()
    stored = templates.get(run.template_name, run.template_version)
    if stored is None:
        return ()
    result = validate(stored.yaml, templates=templates, root_version=stored.version)
    return () if result.template is None else result.template.metrics
