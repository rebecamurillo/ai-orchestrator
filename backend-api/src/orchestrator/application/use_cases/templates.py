"""Reading, validating, saving and seeding Template Versions (SPEC CAP-3, FR-6, AD-15).

Ten operations under eight rules, and each rule is exactly one rule:

- **`list_templates`** answers `GET /templates` — a straight read, no rule of its own.
- **`list_versions`** answers `GET /templates/{name}/versions`: a name nothing has ever
  stored is `NotFound`, because "no version" and "no such Template" read the same to an
  Operator who typed the name wrong.
- **`get_version`** answers `GET /templates/{name}/{version}`: a stored version re-run
  through `validate()` for its `inputs` (never re-derived by hand, so the screen's table and
  the validator can never disagree) plus `callers_of` for `called_by` and `pinned_by` for
  how many Runs (4.4, AD-15) pin this exact Version.
- **`validate_text`** / **`validate_latest`** answer the two `/validate` routes: the posted
  YAML, or the latest stored version's, run through the one parser and handed back exactly
  as it came out — a validation problem is data, not a refusal (NFR-2).
- **`save_version`** answers `POST /templates/{name}/versions`: `validate()` first, the
  path's `name` and the next version number checked against what it parsed, then stored.
  `TemplateValidationFailed` carries the validator's own errors so the router can answer
  422 with `errors[]` — this module never imports `fastapi` (AD-2), so it cannot raise a
  `Problem` itself.
- **`template_graph`** answers `GET /templates/{name}/{version}/graph`: the stored text
  through the same one validator, and its tree through `build_template_graph`. There is no
  second parser and no second shaping, which is what keeps the diagram and the validator
  from disagreeing (AD-15). `StoredTemplateInvalid` is the case storage is meant to make
  impossible — only validated text is ever saved — carried rather than assumed away, so the
  router has a line and a reason to render instead of a traceback.
- **`graph_text`** / **`graph_latest`** answer the two `/templates/{name}/graph` routes
  (3.6): the posted YAML's shape, and the latest stored version's. `graph_text` is the one
  operation the Templates screen's diagram needs, because the editor holds text that is not
  stored yet and a picture one save behind the editor is the wrong picture. It refuses
  rather than reporting — `TemplateValidationFailed`, the exception `save_version` already
  raises with the validator's own errors — because text that does not validate has no
  graph at all; that is the whole difference from `validate_text`, where a problem is data
  (NFR-2). `graph_latest` is `validate_latest`'s `list_versions` -> `max` in front of
  `template_graph`, so the stored-invalid case keeps exactly one statement.
- **`seed_shipped`** is `main.py`'s start-up step: every shipped file, validated against
  whatever this repository already holds, inserted only when its hash is new. Files are
  read off disk by `infrastructure/templates_loader.py` — this module performs no I/O of
  its own — and may name callees in any order: a file whose callee is not yet stored is
  retried after the round that stores it, so `story.yaml` need not sort before `epic.yaml`.
  A file still failing once no file in a round made progress is a real error, not an
  ordering problem, and stops start-up (`ShippedTemplateInvalid`).

`_calls_of` is why `TemplateVersion.calls` is trustworthy: it walks the tree `validate()`
just built — not the raw YAML a second time — so a save can never pin a callee list that
disagrees with what the file actually declares.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from orchestrator.application.graph import Graph, build_template_graph
from orchestrator.application.templates.calls import check_callers
from orchestrator.application.templates.model import (
    ForEach,
    InputDecl,
    ParsedTemplate,
    Step,
    ValidationError,
    ValidationResult,
)
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import (
    TemplateCaller,
    TemplateCallRef,
    TemplateRef,
    TemplateSummary,
    TemplateVersion,
    call_ref,
)
from orchestrator.domain.errors import Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.templates import TemplateVersionRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork

#: The first version a Template's name ever gets.
FIRST_VERSION = 1


@dataclass(frozen=True)
class TemplatePorts:
    """Everything a Template use case reaches the outside world through."""

    uow: UnitOfWork
    templates: TemplateVersionRepository
    clock: Clock


@dataclass(frozen=True)
class TemplateVersionDetail:
    """The read model `GET /templates/{name}/{version}` renders.

    `pinned_by` defaults to `0` so a fixture built before 4.4 (3.1's own, and this file's
    `test_template_version_out_of_a_detail_hardcodes_pinned_by_zero`) still constructs one
    without naming it; `get_version` below is the only caller that fills it with a real
    count.
    """

    template: TemplateVersion
    called_by: tuple[TemplateCaller, ...]
    inputs: tuple[InputDecl, ...]
    pinned_by: int = 0


@dataclass(frozen=True)
class SeedResult:
    """One shipped file's outcome. `inserted_as` is `None` when its hash was already stored."""

    name: str
    inserted_as: int | None


class TemplateValidationFailed(Exception):
    """`save_version`'s YAML did not validate. Carries the errors for the router to render."""

    def __init__(self, errors: tuple[ValidationError, ...]) -> None:
        super().__init__(f"{len(errors)} validation error(s)")
        self.errors = errors


class StoredTemplateInvalid(RuntimeError):
    """A stored Template Version no longer validates, so no graph can be built from it.

    Storage only ever accepts text `validate()` passed, so reaching this is a defect rather
    than a request the caller got wrong — which is why it is a 500 and not a 422. It carries
    the validator's own errors, the way `TemplateValidationFailed` does, so the refusal names
    the line and the reason instead of saying only that something went wrong.
    """

    def __init__(self, name: str, version: int, errors: tuple[ValidationError, ...]) -> None:
        problems = "; ".join(f"line {error.line}: {error.reason}" for error in errors)
        super().__init__(f"stored template {name}@{version} is invalid: {problems}")
        self.name = name
        self.version = version
        self.errors = errors


#: One still-failing file's name and the validator's errors against it.
ShippedFailure = tuple[str, tuple[ValidationError, ...]]


class ShippedTemplateInvalid(RuntimeError):
    """One or more shipped Templates failed `validate()`; start-up must not proceed.

    Carries every file still failing in the round that made no progress at all — not only
    the first — so a genuinely broken file is never hidden behind a second one that is
    merely still waiting on a callee that will never land.
    """

    def __init__(self, failures: tuple[ShippedFailure, ...]) -> None:
        parts = [
            f"{name!r} ({'; '.join(f'line {e.line}: {e.reason}' for e in errors)})"
            for name, errors in failures
        ]
        super().__init__(f"shipped template(s) invalid: {', '.join(parts)}")
        self.failures = failures


def list_templates(ports: TemplatePorts) -> list[TemplateSummary]:
    """Every stored Template name, its versions, and its latest description."""
    return ports.templates.list()


def list_versions(ports: TemplatePorts, name: str) -> list[int]:
    """Every version number stored under `name`, ascending. Unknown to this store is 404."""
    return stored_versions(ports.templates, name)


def stored_versions(templates: TemplateVersionRepository, name: str) -> list[int]:
    """Every version stored under `name`, ascending; `NotFound` when nothing is stored."""
    versions = templates.list_versions(name)
    if not versions:
        raise NotFound(f"no template named {name!r}")
    return versions


def latest_version(templates: TemplateVersionRepository, name: str) -> int:
    """The highest version stored under `name` — what dispatching *by name* resolves to.

    AD-7/AD-15: a Run pins a version, but *which* version a configured name means is read
    off the store at dispatch time rather than written into product code (Operator decision
    2026-09-30: no template name hardcoded in product code — and no version beside it).
    Takes the repository rather than a `TemplatePorts` so the two dispatchers that are not
    Template use cases (`repositories.init_repository`, `harness_readiness.start`) can call
    it with the port `create_run` already holds.
    """
    return max(stored_versions(templates, name))


def get_version(ports: TemplatePorts, name: str, version: int) -> TemplateVersionDetail:
    """One stored version, its `inputs` re-derived, its callers looked up, and its `pinned_by`
    counted (AD-15, 4.4)."""
    stored = ports.templates.get(name, version)
    if stored is None:
        raise NotFound(f"no template {name!r} version {version}")
    result = validate(stored.yaml, templates=ports.templates)
    inputs = result.template.inputs if result.template is not None else ()
    called_by = tuple(ports.templates.callers_of(name, version))
    pinned_by = ports.templates.pinned_by(name, version)
    return TemplateVersionDetail(
        template=stored, called_by=called_by, inputs=inputs, pinned_by=pinned_by
    )


def template_graph(ports: TemplatePorts, name: str, version: int) -> Graph:
    """One stored version's shape: nodes, edges and loop groups. Unknown is 404."""
    stored = ports.templates.get(name, version)
    if stored is None:
        raise NotFound(f"no template {name!r} version {version}")
    result = validate(stored.yaml, templates=ports.templates)
    if result.errors:
        raise StoredTemplateInvalid(name, version, result.errors)
    parsed = result.template
    assert parsed is not None  # validate() never leaves both empty
    return build_template_graph(parsed)


def graph_text(ports: TemplatePorts, yaml_text: str) -> Graph:
    """The posted YAML's shape, validated but never stored. Invalid text has no graph."""
    result = validate(yaml_text, templates=ports.templates)
    if result.errors:
        raise TemplateValidationFailed(result.errors)
    parsed = result.template
    assert parsed is not None  # validate() never leaves both empty
    return build_template_graph(parsed)


def graph_latest(ports: TemplatePorts, name: str) -> Graph:
    """The latest stored version's shape. Unknown to this store is 404."""
    return template_graph(ports, name, latest_version(ports.templates, name))


def validate_text(ports: TemplatePorts, yaml_text: str) -> ValidationResult:
    """The posted YAML, validated but never stored."""
    return validate(yaml_text, templates=ports.templates)


def validate_latest(ports: TemplatePorts, name: str) -> ValidationResult:
    """The latest stored version's YAML, re-validated. Unknown to this store is 404."""
    stored = ports.templates.get(name, latest_version(ports.templates, name))
    assert stored is not None  # `latest_version` came from `list_versions` on this store
    return validate(stored.yaml, templates=ports.templates)


def save_version(ports: TemplatePorts, name: str, yaml_text: str) -> TemplateVersion:
    """Validate, check the path's `name` and the next version number, then store."""
    result = validate(yaml_text, templates=ports.templates)
    if result.errors:
        raise TemplateValidationFailed(result.errors)
    parsed = result.template
    assert parsed is not None  # validate() never leaves both empty
    if parsed.name != name:
        raise Invalid(f"name must be {name}")
    next_version = _next_version(ports.templates, name)
    if parsed.version != next_version:
        raise Invalid(f"version must be {next_version}")
    stranded = check_callers(name, yaml_text, _following_callers(ports.templates, name))
    if stranded:
        raise TemplateValidationFailed(tuple(stranded))
    stored = TemplateVersion(
        id=new_id(),
        name=name,
        version=next_version,
        yaml=yaml_text,
        hash=_hash(yaml_text),
        calls=_calls_of(parsed),
        created_at=ports.clock.now(),
    )
    ports.templates.add_version(stored, description=parsed.description)
    ports.uow.commit()
    return stored


def seed_shipped(ports: TemplatePorts, files: Sequence[tuple[str, str]]) -> list[SeedResult]:
    """Seed every shipped file, in whatever order lets each one's callees land first."""
    pending = list(files)
    results: list[SeedResult] = []
    while pending:
        progressed, pending = _seed_one_round(ports, pending, results)
        if not progressed:
            raise ShippedTemplateInvalid(
                tuple(
                    (name, validate(text, templates=ports.templates).errors)
                    for name, text in pending
                )
            )
    ports.uow.commit()
    return results


def _seed_one_round(
    ports: TemplatePorts, pending: list[tuple[str, str]], results: list[SeedResult]
) -> tuple[bool, list[tuple[str, str]]]:
    """One pass over the not-yet-seeded files; `True` when at least one was seeded."""
    progressed = False
    still_pending: list[tuple[str, str]] = []
    for name, text in pending:
        outcome = validate(text, templates=ports.templates)
        if outcome.errors:
            still_pending.append((name, text))
            continue
        assert outcome.template is not None
        results.append(_seed_file(ports, name, text, outcome.template))
        progressed = True
    return progressed, still_pending


def _seed_file(ports: TemplatePorts, name: str, text: str, parsed: ParsedTemplate) -> SeedResult:
    digest = _hash(text)
    existing = ports.templates.list_versions(name)
    for number in existing:
        stored = ports.templates.get(name, number)
        if stored is not None and stored.hash == digest:
            return SeedResult(name=name, inserted_as=None)
    next_version = max(existing) + 1 if existing else FIRST_VERSION
    version = TemplateVersion(
        id=new_id(),
        name=name,
        version=next_version,
        yaml=text,
        hash=digest,
        calls=_calls_of(parsed),
        created_at=ports.clock.now(),
    )
    ports.templates.add_version(version, description=parsed.description)
    return SeedResult(name=name, inserted_as=next_version)


# --- the rules every write shares ---------------------------------------------------------


def _next_version(templates: TemplateVersionRepository, name: str) -> int:
    """`max(existing) + 1`, or `1` for a name nothing has stored yet."""
    existing = templates.list_versions(name)
    return max(existing) + 1 if existing else FIRST_VERSION


def _hash(yaml_text: str) -> str:
    """The digest a stored version carries — of the exact text saved, byte for byte."""
    return hashlib.sha256(yaml_text.encode()).hexdigest()


def _following_callers(
    templates: TemplateVersionRepository, name: str
) -> list[tuple[TemplateRef, str]]:
    """Every stored version that calls `name` unpinned, with its text — the callers a new
    version of `name` must still satisfy. Asked at a version nothing holds yet, so a pinned
    caller cannot match and only the followers come back."""
    unheld = _next_version(templates, name)
    found: list[tuple[TemplateRef, str]] = []
    for caller in templates.callers_of(name, unheld):
        stored = templates.get(caller.name, caller.version)
        assert stored is not None  # callers_of answers only stored versions
        found.append((TemplateRef(name=caller.name, version=caller.version), stored.yaml))
    return found


def _calls_of(parsed: ParsedTemplate) -> tuple[TemplateCallRef, ...]:
    """Every `uses: template` step's callee, in file order — root and one `for_each` deep.

    Walks the tree `validate()` already built, never the raw YAML: this is what keeps a
    saved `calls` list unable to disagree with what the file declares (AD-15).
    """
    refs: list[TemplateCallRef] = []
    for entry in parsed.steps:
        if isinstance(entry, ForEach):
            refs.extend(ref for ref in (_call_ref(step) for step in entry.steps) if ref)
        else:
            ref = _call_ref(entry)
            if ref is not None:
                refs.append(ref)
    return tuple(refs)


def _call_ref(step: Step) -> TemplateCallRef | None:
    if step.call is None:
        return None
    return call_ref(step.call.name, step.call.version)
