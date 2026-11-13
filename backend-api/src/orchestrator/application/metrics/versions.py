"""What a result version adds to the computed values: carried figures and origin (RM-3).

Pure: no repository is read here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from uuid import UUID

from orchestrator.application.metrics.inputs import AttemptInputs, RunInputs
from orchestrator.application.metrics.scopes import repository_of, scopes_of
from orchestrator.application.metrics.values import NOT_RECORDED, MetricValue
from orchestrator.domain.entities.metric_results import Origin, StoredMetricValue
from orchestrator.domain.ids import new_id

SPANS_HARNESSES = "spans_harnesses"
NO_MODEL_CALLED = "no_model_called"
SPANS_MODELS = "spans_models"
SPANS_REPOSITORIES = "spans_repositories"
NO_REPOSITORY_SCOPE = "no_repository_scope"
COMMIT_MISSING = "commit_missing"
NO_REPOSITORY_RECORD = "no_repository_record"

#: Scope types that cover every attempt of the Run.
_WHOLE_RUN = frozenset({"run", "park", "tool", "conversation"})

ValueKey = tuple[str, str, str, str | None, str | None, str | None]


def _key(value: MetricValue | StoredMetricValue) -> ValueKey:
    return (
        value.metric_id,
        value.scope_type,
        value.scope_key,
        value.source,
        value.role,
        value.model,
    )


def carry_forward(
    values: Sequence[MetricValue],
    earlier: Sequence[tuple[int, Sequence[StoredMetricValue]]],
) -> list[MetricValue]:
    """Replace each `not recorded` value with the newest earlier figure for the same key.

    `earlier` is newest first. The carried value keeps the earlier method id and says which
    version it came from; nothing else is ever carried.
    """
    carried: list[MetricValue] = []
    for value in values:
        found = _earlier_figure(value, earlier) if value.missing == NOT_RECORDED else None
        if found is None:
            carried.append(value)
            continue
        n, old = found
        carried.append(
            replace(
                value,
                method_id=old.method_id,
                value_num=old.value_num,
                unit=old.unit,
                missing=old.missing,
                partial_n=old.partial_n,
                partial_m=old.partial_m,
                carried_from=n,
            )
        )
    return carried


def _earlier_figure(
    value: MetricValue, earlier: Sequence[tuple[int, Sequence[StoredMetricValue]]]
) -> tuple[int, StoredMetricValue] | None:
    wanted = _key(value)
    for n, stored in earlier:
        for old in stored:
            if old.value_num is not None and _key(old) == wanted:
                return n, old
    return None


def _scope_attempts(value: MetricValue, inputs: RunInputs) -> list[AttemptInputs]:
    if value.scope_type in _WHOLE_RUN:
        return list(inputs.attempts)
    if value.scope_type == "gate":
        return [a for a in inputs.attempts if a.row.path == value.scope_key]
    if value.scope_type == "model":
        return [a for a in inputs.attempts if a.attempt.model == value.scope_key]
    wanted = (value.scope_type, value.scope_key)
    return [
        a
        for a in inputs.attempts
        if wanted in {(s.scope_type, s.key) for s in scopes_of(inputs, a, [value.scope_type])}
    ]


def _one(found: set[str], many: str, none: str) -> tuple[str | None, str | None]:
    if len(found) == 1:
        return next(iter(found)), None
    return None, many if found else none


def origin_of(value: MetricValue, inputs: RunInputs) -> Origin:
    """Where `value` comes from: the Run, and the harness, model and repository of its scope."""
    run = inputs.run
    attempts = _scope_attempts(value, inputs)
    harness: str | None
    harness, harness_na = _one(
        {a.attempt.harness for a in attempts if a.attempt.harness}, SPANS_HARNESSES, NO_MODEL_CALLED
    )
    model: str | None
    model_na: str | None
    if value.model is not None:
        model, model_na = value.model, None
    else:
        model, model_na = _one(
            {a.attempt.model for a in attempts if a.attempt.model}, SPANS_MODELS, NO_MODEL_CALLED
        )
    known = [r.path for r in inputs.run_repositories]
    repository: str | None
    repository_na: str | None
    if value.repository is not None:
        repository, repository_na = value.repository, None
    else:
        repository, repository_na = _one(
            {repository_of(a.row, known) for a in attempts},
            SPANS_REPOSITORIES,
            NO_REPOSITORY_SCOPE,
        )
    branch, commit, base = _repository_facts(inputs, repository)
    reason = repository_na or NO_REPOSITORY_RECORD
    return Origin(
        project_id=run.project_id,
        run_id=run.id,
        template_name=run.template_name,
        template_version=run.template_version,
        harness=harness,
        harness_na=harness_na,
        origin_model=model,
        origin_model_na=model_na,
        origin_repository=repository,
        origin_repository_na=repository_na,
        branch=branch[0],
        branch_na=branch[1] or (None if branch[0] else reason),
        commit=commit[0],
        commit_na=commit[1] or (None if commit[0] else reason),
        base_commit=base[0],
        base_commit_na=base[1] or (None if base[0] else reason),
    )


Fact = tuple[str | None, str | None]


def _repository_facts(inputs: RunInputs, repository: str | None) -> tuple[Fact, Fact, Fact]:
    record = next((r for r in inputs.run_repositories if r.path == repository), None)
    if record is None:
        return (None, None), (None, None), (None, None)
    head = record.head_pushed or record.head_local_at_end
    return (
        (record.branch, None),
        (head, None if head else COMMIT_MISSING),
        (record.base_tip, None),
    )


def to_stored(value: MetricValue, version_id: UUID, origin: Origin) -> StoredMetricValue:
    return StoredMetricValue(
        id=new_id(),
        version_id=version_id,
        metric_id=value.metric_id,
        method_id=value.method_id,
        scope_type=value.scope_type,
        scope_key=value.scope_key,
        scope_label=value.scope_label,
        role=value.role,
        model=value.model,
        repository=value.repository,
        attempt_n=value.attempt_n,
        source=value.source,
        value_num=value.value_num,
        unit=value.unit,
        missing=value.missing,
        partial_n=value.partial_n,
        partial_m=value.partial_m,
        carried_from=value.carried_from,
        origin=origin,
    )
