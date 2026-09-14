"""Why a shell row has nothing to run, in the Operator's terms rather than the plan's.

A `run:` row whose command resolves to nothing is `skipped` — but "skipped" alone is not
actionable, and the difference between the two ways to get there is the whole point:

- the row asked a Repository for a command it does not state, which is a box the Operator
  can go and fill in, so the reason names the field: `skipped · no unit_test_command`;
- the row's command resolved to nothing without naming a Repository command at all, which
  is the Template's business and not the Repository's: `skipped · no command`.

The field is *named*, never assumed. A Repository states three commands — `install_command`
for the toolchain, `unit_test_command` for the per-Story gate, `quality_gate_command` for
the slow one — and any of them can be the reason a row is empty, so a reason welded to one
of the three tells two thirds of Operators the wrong thing to fix.

Its own module because `rows.py` is the walker and this is a sentence about one row; the
walker imports it, never the other way round, so the declared command comes in as a value
rather than as a `Step` this module would have to know the shape of.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.templates.plan_model import REASON_NO_COMMAND, reason_no_field
from orchestrator.application.templates.substitute import field_named

#: The entity whose missing command makes a row `skipped · no <field>` rather than
#: `skipped · no command`. The entity is checked as well as the field, because
#: `{{project.quality_gate_command}}` names no Repository and asks for nothing: the pair
#: is one of `expressions.ENTITY_FIELDS`' own.
COMMAND_ENTITY = "repository"

#: The Repository command every shell row asked for before the gates were tiered. Kept as
#: a name because the relationship it stands for is now the rule rather than the exception:
#: a reason may name any field of `ENTITY_FIELDS[COMMAND_ENTITY]`, and this is one of them.
QUALITY_GATE_FIELD = "quality_gate_command"


def empty_command_reason(declared: Any) -> str:
    """The reason for a shell row whose command resolved to nothing.

    `declared` is what the Template wrote, before substitution — the question is about the
    expression, not about its answer, which is why the resolved value cannot decide it.
    """
    field = field_named(declared, COMMAND_ENTITY)
    return reason_no_field(field) if field is not None else REASON_NO_COMMAND
