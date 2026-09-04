"""The HTTP shape of a Project — and the layer that turns a broken rule into an `errors[]`.

The rules themselves live in `domain/entities/project.py`; this module calls them from
pydantic validators for one reason: a validator's failure is a `RequestValidationError`,
which `api/errors.py` renders as `errors[{path, reason}]`, and `path` is what the form in
2.5 puts the message beside. The same refusal raised inside a use case would arrive as a
`detail` string with no field attached to it.

Three shapes differ between the two writes, and each difference is deliberate:

- **`POST` requires every value**; there is nothing stored to keep.
- **`PUT` makes the value optional**, and an entry without one keeps the stored ciphertext.
  This is how a form that never received a secret can send the set back without losing it.
- **Neither accepts a value on the way out.** `ProjectRead` carries `masked` and no `value`
  field at all, so no serialisation of it can leak one, whatever a router passes in.

`log_prompt_content` is carried through as `None` when the payload omits it. A create
resolves that to `LOG_PROMPT_CONTENT_DEFAULT` and an update resolves it to the value
already stored, and only the use case can tell those apart — resolving it here would make
every `PUT` that leaves the field out silently reset the Operator's choice.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Final
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field

from orchestrator.api.schemas.common import StorableText, UtcTimestamp
from orchestrator.application.use_cases.projects import EnvVarInput, ProjectDraft
from orchestrator.domain.entities.project import (
    ENV_NAME_REASON,
    RESERVED_ENV_REASON,
    ProjectView,
    is_reserved_env_name,
    is_valid_env_name,
)

#: Said back to the Operator when one payload names the same variable twice.
DUPLICATE_ENV_REASON = "duplicate variable name"

#: A Project is identified by its name on the Board; the column and the form agree on this.
NAME_MAX_LENGTH: Final = 80

#: Said back to the Operator when a context path is not one a clone can resolve.
CONTEXT_PATH_REASON = "a context path is relative to the repository root"

#: The segment that would walk out of the worktree the agent reads (AD-14).
PARENT_SEGMENT = ".."


def _repo_relative(path: str) -> str:
    """A context path names a file inside the clone, and nothing above or outside it.

    An absolute path escapes `/work/{slug}` entirely, `..` walks out of it a segment at a
    time, and an empty entry names nothing at all — each is a path the agent step in Epic 4
    could not resolve, so it is refused here where the Operator can still see the field.
    """
    stripped = path.strip()
    if not stripped:
        raise ValueError(CONTEXT_PATH_REASON)
    pure = PurePosixPath(stripped)
    if pure.is_absolute() or PARENT_SEGMENT in pure.parts:
        raise ValueError(CONTEXT_PATH_REASON)
    return stripped


ContextPath = Annotated[StorableText, AfterValidator(_repo_relative)]


def _valid_env_name(name: str) -> str:
    """The two name rules, in the order that gives the more specific message first."""
    if not is_valid_env_name(name):
        raise ValueError(ENV_NAME_REASON)
    if is_reserved_env_name(name):
        raise ValueError(RESERVED_ENV_REASON)
    return name


EnvVarName = Annotated[StorableText, AfterValidator(_valid_env_name)]


class EnvVarIn(BaseModel):
    """One requested variable. Without a `value`, the stored ciphertext is kept."""

    name: EnvVarName
    value: StorableText | None = None


class EnvVarCreate(EnvVarIn):
    """One requested variable on a create, where there is nothing to keep."""

    value: StorableText


def _no_duplicate_names[T: EnvVarIn](variables: list[T]) -> list[T]:
    """One name, one value. Two entries named `A` are an edit the Operator did not mean."""
    seen: set[str] = set()
    for variable in variables:
        if variable.name in seen:
            raise ValueError(f"{DUPLICATE_ENV_REASON}: {variable.name}")
        seen.add(variable.name)
    return variables


class MaskedEnvVarOut(BaseModel):
    """One stored variable as it leaves this API: the name, and four characters of the value."""

    name: str
    masked: str


class ProjectRead(BaseModel):
    """A Project as every read returns it. There is no field here that could hold a value."""

    id: UUID
    slug: str
    name: str
    context_text: str
    context_paths: list[str]
    env_vars: list[MaskedEnvVarOut]
    log_prompt_content: bool
    created_at: UtcTimestamp
    updated_at: UtcTimestamp

    @classmethod
    def of(cls, view: ProjectView) -> ProjectRead:
        """Render the use case's masked read model. The only way a Project leaves."""
        return cls.model_validate(view.model_dump())


class ProjectWrite(BaseModel):
    """What both writes have in common, so neither can drift from the other."""

    #: A Project is identified by its name on the Board; an unnamed one names nothing, and
    #: the upper bound is the one the brief states and the unique index has to hold.
    name: Annotated[StorableText, Field(min_length=1, max_length=NAME_MAX_LENGTH)]
    context_text: StorableText = ""
    context_paths: list[ContextPath] = Field(default_factory=list)
    #: `null` means "not stated". On a create that is the instance default
    #: (`LOG_PROMPT_CONTENT_DEFAULT`); on an update it is the value already stored. Neither
    #: resolution happens here: only the use case knows which of the two applies.
    log_prompt_content: bool | None = None

    def _draft(self, env_vars: list[EnvVarIn]) -> ProjectDraft:
        return ProjectDraft(
            name=self.name,
            log_prompt_content=self.log_prompt_content,
            context_text=self.context_text,
            context_paths=tuple(self.context_paths),
            env_vars=tuple(
                EnvVarInput(name=variable.name, value=variable.value) for variable in env_vars
            ),
        )


class ProjectCreate(ProjectWrite):
    """`POST /projects`. Every variable carries its value."""

    env_vars: Annotated[list[EnvVarCreate], AfterValidator(_no_duplicate_names)] = Field(
        default_factory=list
    )

    def as_draft(self) -> ProjectDraft:
        return self._draft(list(self.env_vars))


class ProjectUpdate(ProjectWrite):
    """`PUT /projects/{id}`. A variable without a value keeps the one already stored."""

    env_vars: Annotated[list[EnvVarIn], AfterValidator(_no_duplicate_names)] = Field(
        default_factory=list
    )

    def as_draft(self) -> ProjectDraft:
        return self._draft(self.env_vars)
