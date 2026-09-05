"""Reading, validating, saving and seeding Template Versions (SPEC CAP-3, FR-6, AD-15).

Six operations, and each is exactly one rule:

- **`list_templates`** answers `GET /templates` — a straight read, no rule of its own.
- **`list_versions`** answers `GET /templates/{name}/versions`: a name nothing has ever
  stored is `NotFound`, because "no version" and "no such Template" read the same to an
  Operator who typed the name wrong.
- **`get_version`** answers `GET /templates/{name}/{version}`: a stored version re-run
  through `validate()` for its `inputs` (never re-derived by hand, so the screen's table and
  the validator can never disagree) plus `callers_of` for `called_by`. `pinned_by` is always
  `0` here — Epic 4 is the only writer of a pin.
- **`validate_text`** / **`validate_latest`** answer the two `/validate` routes: the posted
  YAML, or the latest stored version's, run through the one parser and handed back exactly
  as it came out — a validation problem is data, not a refusal (NFR-2).
- **`save_version`** answers `POST /templates/{name}/versions`: `validate()` first, the
  path's `name` and the next version number checked against what it parsed, then stored.
  `TemplateValidationFailed` carries the validator's own errors so the router can answer
  422 with `errors[]` — this module never imports `fastapi` (AD-2), so it cannot raise a
  `Problem` itself.
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

from orchestrator.application.templates.model import (
    ForEach,
    InputDecl,
    ParsedTemplate,
    Step,
    ValidationError,
    ValidationResult,
)
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateRef, TemplateSummary, TemplateVersion
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
    """The read model `GET /templates/{name}/{version}` renders (`pinned_by` is Epic 4's)."""

    template: TemplateVersion
    called_by: tuple[TemplateRef, ...]
    inputs: tuple[InputDecl, ...]


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
    versions = ports.templates.list_versions(name)
    if not versions:
        raise NotFound(f"no template named {name!r}")
    return versions


def get_version(ports: TemplatePorts, name: str, version: int) -> TemplateVersionDetail:
    """One stored version, its `inputs` re-derived and its callers looked up."""
    stored = ports.templates.get(name, version)
    if stored is None:
        raise NotFound(f"no template {name!r} version {version}")
    result = validate(stored.yaml, templates=ports.templates)
    inputs = result.template.inputs if result.template is not None else ()
    called_by = tuple(ports.templates.callers_of(name, version))
    return TemplateVersionDetail(template=stored, called_by=called_by, inputs=inputs)


def validate_text(ports: TemplatePorts, yaml_text: str) -> ValidationResult:
    """The posted YAML, validated but never stored."""
    return validate(yaml_text, templates=ports.templates)


def validate_latest(ports: TemplatePorts, name: str) -> ValidationResult:
    """The latest stored version's YAML, re-validated. Unknown to this store is 404."""
    versions = ports.templates.list_versions(name)
    if not versions:
        raise NotFound(f"no template named {name!r}")
    stored = ports.templates.get(name, max(versions))
    assert stored is not None  # `max(versions)` came from `list_versions` on this same store
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


def _calls_of(parsed: ParsedTemplate) -> tuple[TemplateRef, ...]:
    """Every `uses: template` step's callee, in file order — root and one `for_each` deep.

    Walks the tree `validate()` already built, never the raw YAML: this is what keeps a
    saved `calls` list unable to disagree with what the file declares (AD-15).
    """
    refs: list[TemplateRef] = []
    for entry in parsed.steps:
        if isinstance(entry, ForEach):
            refs.extend(ref for ref in (_call_ref(step) for step in entry.steps) if ref)
        else:
            ref = _call_ref(entry)
            if ref is not None:
                refs.append(ref)
    return tuple(refs)


def _call_ref(step: Step) -> TemplateRef | None:
    if step.call is None:
        return None
    return TemplateRef(name=step.call.name, version=step.call.version)
