"""Filling in a Template's `{{ }}` once a Run has values for them.

Substitution, not evaluation — the same grammar `expressions.py` validates, read from the
other side. The regexes and the entity whitelist are imported from there rather than copied,
because a second copy is exactly how what the editor accepts and what a Run actually
dispatches would come to disagree (AD-15).

Two rules decide what a `{{ }}` becomes:

- **A string that is exactly one bound variable passes its value through whole.**
  `story: "{{story}}"` binds the list-file entry itself — a mapping — to the callee's
  `story` input, because a callee handed the entry's `str()` could not read `story.id` off
  it. That is what makes `epic@1`'s call to `story@1` work at all.
- **Every other string is text with holes in it**, so each hole becomes text: `""` for a
  value nobody bound, `str(...)` for everything else. Never the four characters `None`,
  which is what a Run would otherwise hand to a shell.

A name nobody bound is the same as a value nobody gave: `model: "{{model}}"` on a Run that
chose no model resolves to `""`, which is also what makes an unset `quality_gate_command`
reach the walker as an empty command it can skip.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from re import Match
from typing import Any

from orchestrator.application.dto import ProjectSnapshot, RepositorySnapshot
from orchestrator.application.templates.expressions import (
    BARE_FIELD,
    ENTITY_FIELDS,
    EXPRESSION,
    VARIABLE,
    WHOLE_VARIABLE,
)

#: Which whitelist an entity snapshot is read against. Keyed by the class rather than by the
#: input's name, because a Template may call its Repository input anything it likes.
ENTITY_KINDS: dict[type, str] = {
    ProjectSnapshot: "project",
    RepositorySnapshot: "repository",
}


def resolve(value: Any, scope: Mapping[str, Any]) -> Any:
    """One `with` value with every expression in it filled in from the scope."""
    if isinstance(value, str):
        return _text(value, scope)
    if isinstance(value, Mapping):
        return {key: resolve(item, scope) for key, item in value.items()}
    if isinstance(value, Sequence):
        return [resolve(item, scope) for item in value]
    return value


def lookup(name: str, field: str | None, scope: Mapping[str, Any]) -> Any:
    """What `{{name}}` or `{{name.field}}` refers to, or `None` when it refers to nothing.

    A field of an entity snapshot is read only when `ENTITY_FIELDS` allows it, so
    `{{repository.slug}}` is nothing here for the same reason it is `unknown field` there.
    A field of a list-file entry is whatever the entry holds; a field of anything else — a
    string, a number — does not exist.
    """
    value = scope.get(name)
    if field is None:
        return value
    entity = ENTITY_KINDS.get(type(value))
    if entity is not None:
        return getattr(value, field) if field in ENTITY_FIELDS[entity] else None
    if isinstance(value, Mapping):
        return value.get(field)
    return None


def names_field(value: Any, entity: str, field: str) -> bool:
    """Whether a declared value asks for one named field of one named entity.

    The planner's `skipped` rule needs to tell `run: "{{repository.quality_gate_command}}"`
    on a Repository that states none apart from a command that simply resolved to nothing,
    and that is a question about the expression rather than about its answer. Both halves
    are matched: `{{project.quality_gate_command}}` asks a Project for a field it does not
    have, which is `no command` and not a Repository's missing quality gate. Here rather
    than in the walker because it reads the same grammar the rest of this module does.
    """
    if not isinstance(value, str):
        return False
    return any(
        (reference := VARIABLE.match(inner)) is not None
        and (reference.group(1), reference.group(2)) == (entity, field)
        for inner in EXPRESSION.findall(value)
    )


def paused(condition: str | None, scope: Mapping[str, Any]) -> bool:
    """Whether a `pause_*_when` condition holds for what is bound now.

    A condition is written bare — `story.done_checkpoint`, never in braces — so it is read
    here rather than through `resolve`: the answer is a truth value, not text. A Template
    that declared none pauses at nothing, and so does one whose condition the grammar never
    allowed, which `validate()` has already refused.
    """
    if condition is None:
        return False
    reference = BARE_FIELD.match(condition)
    if reference is None:
        return False
    return bool(lookup(reference.group(1), reference.group(2), scope))


def _text(value: str, scope: Mapping[str, Any]) -> Any:
    """The whole-variable rule, then interpolation for everything else."""
    whole = WHOLE_VARIABLE.match(value)
    if whole is not None and whole.group(1) in scope:
        return scope[whole.group(1)]
    return EXPRESSION.sub(lambda match: _filled(match, scope), value)


def _filled(match: Match[str], scope: Mapping[str, Any]) -> str:
    """One `{{ }}` as text. An expression the grammar never allowed fills in as nothing.

    `validate()` refuses such a Template, so this is the answer to a question no shipped
    file asks — but `resolve` is a total function, and returning the braces verbatim would
    put them in a command line.
    """
    reference = VARIABLE.match(match.group(1))
    if reference is None:
        return ""
    value = lookup(reference.group(1), reference.group(2), scope)
    return "" if value is None else str(value)
