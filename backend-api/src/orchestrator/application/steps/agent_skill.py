"""The `agent` kind's last line of defence: a skill this instance cannot resolve (AD-9).

A harness handed a skill name it cannot resolve does **not** fail. It improvises — in the
Run this module was written for, `claude` was dispatched with `skill: spec-gate`, could not
resolve it, worked for 177 seconds, edited a protected `SPEC.md`, produced none of the
expected artifact, and the row only then parked on the missing output. A silently improvising
agent is worse than a hard failure, so the name is checked against the instance's own catalog
before the dispatch (hub-Run operations, skills install fix, 2026-09-24).

Pre-flight is the *first* line of defence and refuses such a Run before it is created
(`application/preflight/lists.py::installed_skill_lines`). This one catches what pre-flight
cannot: a Run planned while the catalog said one thing and dispatched after it said another.

**What it never refuses.** A row that names no skill — the `prompt:` and `intent:` dispatch
forms (`application/templates/agent_row.py`) carry no `skill` key — and a catalog that cannot
answer. An unreadable manifest says nothing about the skill, and a row already planned and
running must not be parked on no evidence; the `fail` pre-flight raises over exactly that
condition is where an unreadable catalog is answered.
"""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext
from orchestrator.domain.values import Park, StepResult

#: The `with` key `agent_row.py` writes the skill name on the row as.
SKILL_KEY = "skill"

#: The reason this row leaves, in `agent.py::UNKNOWN_HARNESS`'s own shape.
UNKNOWN_SKILL = "skill misconfigured: {name} is not installed in this instance"


def verify(ctx: StepContext) -> StepResult | None:
    """The park a skill this instance cannot resolve is, or `None` to dispatch as usual."""
    catalog = ctx.ports.skill_catalog
    if catalog is None:
        return None
    name = ctx.with_resolved.get(SKILL_KEY)
    if not isinstance(name, str) or not name:
        return None
    installed = catalog.installed_skills()
    if installed is None or name in installed:
        return None
    reason = UNKNOWN_SKILL.format(name=name)
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        reason=reason,
        park=Park(kind="misconfigured", reason=reason, path=ctx.row.path),
    )
