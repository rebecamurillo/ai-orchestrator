"""Resolving the pinned Template tree out of storage, and handing it to the pure planner.

`plan_run` takes a `ResolvedTree` rather than a repository on purpose: a planner that could
look a Template up could look one up twice and plan a Run from two different versions of
the same file. This module is the seam where the looking-up happens — once, before anything
pure begins (AD-7, AD-15) — and it is thin by design: everything it does is walk the call
tree through the one validator there is and call `plan_run`.

The walk follows `TemplateCall`s rather than `TemplateVersion.calls`, because the tree the
plan is expanded from is the tree the *files* declare; `calls` is the pin the save recorded
and 3.x's own tests already hold it to that. A callee reached by two callers is resolved
once, so `ResolvedTree.pinned_versions()` is a set of pins in walk order rather than a bag.

An unpinned call (no `version`) is resolved here to the callee's latest stored version —
once per name, recorded in `ResolvedTree.latest` — so the plan, the rows and the Run's
`pinned_versions` all name one concrete integer and a save made after this point never
reaches this Run (AD-15).

A version the store does not hold and a stored version that no longer validates are the
same outcome to the Operator — this Run cannot be planned — so both are one `PlanError`
naming the version at fault, and `Invalid` already answers 422 (`api/errors.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.application.dto import RunInputs
from orchestrator.application.templates.calls import resolve_callee
from orchestrator.application.templates.model import ForEach, ParsedTemplate
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import (
    CALLEE_NOT_RESOLVED,
    Plan,
    PlanError,
    ResolvedTree,
)
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateRef
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.templates import TemplateVersionRepository


@dataclass(frozen=True)
class PlanPorts:
    """The two ports planning a Run reaches the outside world through."""

    templates: TemplateVersionRepository
    git: Git


def resolve_tree(templates: TemplateVersionRepository, ref: TemplateRef) -> ResolvedTree:
    """The root Template and every callee it reaches, each parsed once, in walk order."""
    root = _parsed(templates, ref.name, ref.version)
    callees: list[ParsedTemplate] = []
    latest: dict[str, int] = {}
    seen = {(ref.name, ref.version)}
    pending = _calls(root)
    while pending:
        name, written = pending.pop(0)
        number = resolve_callee(templates, name, written)
        if (name, number) in seen:
            continue
        parsed = _parsed(templates, name, number)
        seen.add((name, parsed.version))
        if written is None:
            latest[name] = parsed.version
        callees.append(parsed)
        pending += _calls(parsed)
    return ResolvedTree(root=root, callees=tuple(callees), latest=latest)


def plan_for(
    ports: PlanPorts,
    ref: TemplateRef,
    inputs: RunInputs,
    *,
    base_dir: Path,
    bmad_version: str,
) -> Plan:
    """Plan one Run: resolve the tree, then expand it purely (AD-7)."""
    tree = resolve_tree(ports.templates, ref)
    return plan_run(tree, inputs, git=ports.git, base_dir=base_dir, bmad_version=bmad_version)


def _parsed(templates: TemplateVersionRepository, name: str, version: int | None) -> ParsedTemplate:
    """One stored version through the one parser, or the refusal that it is not usable.

    `version=None` is an unpinned call whose name holds no version at all; `validate()` has
    already refused such a caller, so this is the same refusal spelled `name@latest`.
    """
    stored = None if version is None else templates.get(name, version)
    if stored is None:
        raise _unresolved(name, version)
    result = validate(stored.yaml, templates=templates)
    if result.template is None:
        raise _unresolved(name, version, result.errors[0].line)
    return result.template


def _unresolved(name: str, version: int | None, line: int | None = None) -> PlanError:
    return PlanError(
        reason=CALLEE_NOT_RESOLVED,
        template=name,
        version=version,
        line=line,
        item=f"{name}@{'latest' if version is None else version}",
    )


def _calls(template: ParsedTemplate) -> list[tuple[str, int | None]]:
    """Every `uses: template` step of one file, top level and inside its loop, in order, as
    `(name, version)` with `None` where the file pinned nothing."""
    found: list[tuple[str, int | None]] = []
    for entry in template.steps:
        steps = entry.steps if isinstance(entry, ForEach) else (entry,)
        found += [(step.call.name, step.call.version) for step in steps if step.call is not None]
    return found
