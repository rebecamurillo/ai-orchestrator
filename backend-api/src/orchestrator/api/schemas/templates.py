"""The HTTP shape of Template Versions (SPEC CAP-3): reads, validation, and the next save.

`ValidateOut.errors` and `TemplateVersionOut`'s save-time 422 both reuse `api/errors.py`'s
`ProblemError` rather than a schema of their own — the brief's own acceptance criterion is
that `/validate`'s 200 and `/versions`'s 422 carry "the same errors in `errors[]`", and
reusing the one model is what makes that literally true rather than merely similar.
`version` is a string there (`ProblemError.version: str | None`) where the domain
`ValidationError.version` is `int | None` (3.1); `as_problem_errors` is where that mapping
happens, once, for both routes that need it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

from pydantic import BaseModel, Field

from orchestrator.api.errors import ProblemError
from orchestrator.api.schemas.common import UtcTimestamp
from orchestrator.application.templates.model import InputDecl, Scalar, ValidationError
from orchestrator.application.templates.model import ValidationResult as AppValidationResult
from orchestrator.application.use_cases.templates import TemplateVersionDetail
from orchestrator.domain.entities.template import (
    TemplateCaller,
    TemplateCallRef,
    TemplateRef,
    TemplateSummary,
)

#: A coarse cap on posted YAML text — the largest shipped Template is a few KB, and this
#: guard is what closes (partially: it bounds text length, not `yaml.SafeLoader` alias
#: expansion) the loader-hardening gap 3.1 deferred to this story: "the loader has no
#: input-size ... guard on operator YAML ... Story 3.3 exposes POST /templates/{name}/validate,
#: which is where the guard belongs."
MAX_TEMPLATE_YAML_LENGTH = 200_000

TemplateYaml = Annotated[str, Field(max_length=MAX_TEMPLATE_YAML_LENGTH)]


def as_problem_errors(errors: Sequence[ValidationError]) -> list[ProblemError]:
    """`ValidationError.version` (`int | None`) rendered as `ProblemError.version` (`str`)."""
    return [
        ProblemError(
            template=error.template,
            version=str(error.version) if error.version is not None else None,
            line=error.line,
            reason=error.reason,
        )
        for error in errors
    ]


class TemplateRefOut(BaseModel):
    """One `(name, version)` reference, as `calls` and `called_by` each list them."""

    name: str
    version: int

    @classmethod
    def of(cls, ref: TemplateRef) -> TemplateRefOut:
        return cls(name=ref.name, version=ref.version)


class TemplateCallOut(BaseModel):
    """One `calls` entry: the callee as the file named it — `version` null when unpinned."""

    name: str
    version: Annotated[
        int | None,
        Field(description="The pinned version, or `null` for an unpinned call (latest)."),
    ]

    @classmethod
    def of(cls, ref: TemplateCallRef) -> TemplateCallOut:
        return cls(name=ref.name, version=ref.version)


class TemplateCallerOut(BaseModel):
    """One `called_by` entry; `pinned` false means the caller follows this name's latest."""

    name: str
    version: int
    pinned: Annotated[
        bool,
        Field(
            description=(
                "True when the caller names this exact version; false when it omits "
                "`version` and so follows whatever is latest."
            )
        ),
    ]

    @classmethod
    def of(cls, caller: TemplateCaller) -> TemplateCallerOut:
        return cls(name=caller.name, version=caller.version, pinned=caller.pinned)


class TemplateSummaryOut(BaseModel):
    """One row of `GET /templates`."""

    name: str
    description: str | None
    latest_version: int
    versions: list[int]

    @classmethod
    def of(cls, summary: TemplateSummary) -> TemplateSummaryOut:
        return cls(
            name=summary.name,
            description=summary.description,
            latest_version=summary.latest_version,
            versions=list(summary.versions),
        )


class InputDeclOut(BaseModel):
    """One entry of the Template's `inputs:` map, for the screen's inputs table."""

    name: str
    type: str
    required: bool
    default: Scalar | None
    values: list[str]

    @classmethod
    def of(cls, decl: InputDecl) -> InputDeclOut:
        return cls(
            name=decl.name,
            type=decl.type,
            required=decl.required,
            default=decl.default,
            values=list(decl.values),
        )


class TemplateVersionOut(BaseModel):
    """`GET /templates/{name}/{version}`, and the 201 body a save answers with."""

    name: str
    version: int
    yaml: str
    hash: Annotated[str, Field(description="sha256 hex digest of `yaml`, byte for byte.")]
    calls: list[TemplateCallOut]
    called_by: list[TemplateCallerOut]
    pinned_by: Annotated[
        int,
        Field(
            description=(
                "How many Runs, of any status, pin this exact Version — root or callee "
                "(AD-15, SPEC CAP-4)."
            )
        ),
    ]
    created_at: UtcTimestamp | None
    inputs: list[InputDeclOut]

    @classmethod
    def of(cls, detail: TemplateVersionDetail) -> TemplateVersionOut:
        return cls(
            name=detail.template.name,
            version=detail.template.version,
            yaml=detail.template.yaml,
            hash=detail.template.hash,
            calls=[TemplateCallOut.of(ref) for ref in detail.template.calls],
            called_by=[TemplateCallerOut.of(caller) for caller in detail.called_by],
            pinned_by=detail.pinned_by,
            created_at=detail.template.created_at,
            inputs=[InputDeclOut.of(decl) for decl in detail.inputs],
        )


class ValidateIn(BaseModel):
    """`POST /templates/{name}/validate`."""

    yaml: TemplateYaml


class ValidateOut(BaseModel):
    """`200` from either `/validate` route: problems are data, never a refusal (NFR-2)."""

    errors: list[ProblemError]
    unvalidated: list[str]

    @classmethod
    def of(cls, result: AppValidationResult) -> ValidateOut:
        return cls(
            errors=as_problem_errors(result.errors),
            unvalidated=list(result.unvalidated),
        )


class SaveVersionIn(ValidateIn):
    """`POST /templates/{name}/versions`. Same one field; a distinct name for a distinct route."""
