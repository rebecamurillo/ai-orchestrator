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

A version the store does not hold and a stored version that no longer validates are the
same outcome to the Operator — this Run cannot be planned — so both are one `PlanError`
naming the version at fault, and `Invalid` already answers 422 (`api/errors.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.application.dto import RunInputs
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
    root = _parsed(templates, ref)
    callees: list[ParsedTemplate] = []
    seen = {(ref.name, ref.version)}
    pending = _calls(root)
    while pending:
        call = pending.pop(0)
        if (call.name, call.version) in seen:
            continue
        seen.add((call.name, call.version))
        parsed = _parsed(templates, call)
        callees.append(parsed)
        pending += _calls(parsed)
    return ResolvedTree(root=root, callees=tuple(callees))


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


def _parsed(templates: TemplateVersionRepository, ref: TemplateRef) -> ParsedTemplate:
    """One stored version through the one parser, or the refusal that it is not usable."""
    stored = templates.get(ref.name, ref.version)
    if stored is None:
        raise _unresolved(ref)
    result = validate(stored.yaml, templates=templates)
    if result.template is None:
        raise _unresolved(ref, result.errors[0].line)
    return result.template


def _unresolved(ref: TemplateRef, line: int | None = None) -> PlanError:
    return PlanError(
        reason=CALLEE_NOT_RESOLVED,
        template=ref.name,
        version=ref.version,
        line=line,
        item=f"{ref.name}@{ref.version}",
    )


def _calls(template: ParsedTemplate) -> list[TemplateRef]:
    """Every `uses: template` step of one file, top level and inside its loop, in order."""
    found: list[TemplateRef] = []
    for entry in template.steps:
        steps = entry.steps if isinstance(entry, ForEach) else (entry,)
        found += [
            TemplateRef(name=step.call.name, version=step.call.version)
            for step in steps
            if step.call is not None
        ]
    return found
