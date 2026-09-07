"""What a Run is planned from: the values, not the entities.

`plan_run` is pure (AD-7): two calls with the same tree, the same inputs and the same
scripted `Git` produce equal plans. An entity the planner could re-read is exactly what
would break that, so the Project and the Repository arrive as snapshots — what they said
when the Run was created — and nothing downstream re-resolves them.

Three fields carry a rule the columns alone do not state:

- **The optional commands default to `None`, never to `""`.** A Repository that states no
  `quality_gate_command` and one that states an empty one are the same to the Operator, but
  `None` is the value a substitution can tell apart from a command that runs and produces
  nothing; the planner turns it into `skipped · no quality_gate_command` (FR-8).
- **`values` holds the Template's own declared inputs** — `branch`, `spec_folder`,
  `initiative_folder`, whatever the file declared — read whole and never queried into here.
  The three fields beside it (`base_branch`, `harness`, `model`) are named because every
  Template takes them and the API has a column for each.
- **`model` is `None` when nobody chose one**, which is what makes `{{model}}` resolve to
  the empty string rather than to the four characters `None` (AD-15 substitution rule).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

#: The harness a Run dispatches to when the Operator named none (AD-10).
DEFAULT_HARNESS = "claude"


class ProjectSnapshot(BaseModel):
    """The Project as the Run saw it: its name for a prompt, its slug for a path (AD-14)."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    slug: str


class RepositorySnapshot(BaseModel):
    """The Repository as the Run saw it: where it is, and what it says to run in it."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    slug: str
    url: str
    default_branch: str
    #: `None` means "this Repository states none" — see the module docstring.
    install_command: str | None = None
    quality_gate_command: str | None = None
    unit_test_command: str | None = None
    test_globs: tuple[str, ...] = ()


class RunInputs(BaseModel):
    """Everything a Run was started with, in the form the planner substitutes from."""

    model_config = ConfigDict(frozen=True)

    project: ProjectSnapshot
    repository: RepositorySnapshot
    base_branch: str
    #: The Template's own declared inputs. Built per instance, so two Runs never share one.
    values: dict[str, Any] = Field(default_factory=dict)
    harness: str = DEFAULT_HARNESS
    model: str | None = None
    #: True when the Operator asked for the stories that are already done to run again
    #: (FR-10); it is the one thing that turns the already-done rule off.
    re_review_done: bool = False
