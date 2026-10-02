"""`api/schemas/templates.py` — the read models `.of()` builds, and `as_problem_errors`.

The router's own behaviour is asserted in `tests/unit/test_templates_router.py` over an
ASGI transport; this module is where the mapping itself — domain and application types onto
the wire shape, `ValidationError.version: int | None` onto `ProblemError.version: str |
None` — is pinned without a request in the way.
"""

from __future__ import annotations

from datetime import UTC, datetime

from orchestrator.api.schemas.templates import (
    InputDeclOut,
    TemplateCallerOut,
    TemplateCallOut,
    TemplateRefOut,
    TemplateSummaryOut,
    TemplateVersionOut,
    ValidateOut,
    as_problem_errors,
)
from orchestrator.application.templates.model import InputDecl, ValidationError, ValidationResult
from orchestrator.application.use_cases.templates import TemplateVersionDetail
from orchestrator.domain.entities.template import (
    TemplateCaller,
    TemplateCallRef,
    TemplateRef,
    TemplateSummary,
    TemplateVersion,
)

AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)

#: Named so the comparisons below name no magic number.
LATEST_VERSION = 2
ERROR_LINE = 12


def test_template_ref_out_of_a_ref() -> None:
    assert TemplateRefOut.of(TemplateRef(name="story", version=1)) == TemplateRefOut(
        name="story", version=1
    )


def test_template_summary_out_of_a_summary() -> None:
    summary = TemplateSummary(
        name="epic", description="the loop", latest_version=2, versions=(1, 2)
    )

    out = TemplateSummaryOut.of(summary)

    assert out.name == "epic"
    assert out.description == "the loop"
    assert out.latest_version == LATEST_VERSION
    assert out.versions == [1, 2]


def test_input_decl_out_of_a_decl() -> None:
    decl = InputDecl(
        line=3, name="spec_folder", type="path", required=True, default=None, values=()
    )

    out = InputDeclOut.of(decl)

    assert (out.name, out.type, out.required, out.default, out.values) == (
        "spec_folder",
        "path",
        True,
        None,
        [],
    )


def test_template_version_out_of_a_detail_hardcodes_pinned_by_zero() -> None:
    stored = TemplateVersion(
        name="leaf",
        version=1,
        yaml="name: leaf\nversion: 1\nsteps: []\n",
        hash="sha",
        calls=(TemplateRef(name="child", version=1),),
        created_at=AT,
    )
    detail = TemplateVersionDetail(
        template=stored,
        called_by=(TemplateCaller(name="root", version=1, pinned=True),),
        inputs=(InputDecl(line=1, name="x", type="string"),),
    )

    out = TemplateVersionOut.of(detail)

    assert out.name == "leaf"
    # revised to the call/caller shapes by the Operator decision 2026-10-02, editable
    # workflows: a `uses: template` call may omit `version`; it resolves to the callee's
    # latest at validate and plan time; no cascade.
    assert out.calls == [TemplateCallOut(name="child", version=1)]
    assert out.called_by == [TemplateCallerOut(name="root", version=1, pinned=True)]
    assert out.pinned_by == 0
    assert out.created_at == AT
    assert [decl.name for decl in out.inputs] == ["x"]


def test_as_problem_errors_renders_an_int_version_as_a_string() -> None:
    errors = (ValidationError(template="epic", version=1, line=12, reason="unknown kind"),)

    rendered = as_problem_errors(errors)

    assert rendered[0].version == "1"
    assert rendered[0].line == ERROR_LINE
    assert rendered[0].reason == "unknown kind"


def test_as_problem_errors_leaves_a_missing_version_as_none() -> None:
    errors = (ValidationError(template=None, version=None, line=1, reason="invalid yaml"),)

    rendered = as_problem_errors(errors)

    assert rendered[0].version is None
    assert rendered[0].template is None


def test_validate_out_of_a_result_with_errors() -> None:
    result = ValidationResult(
        errors=(ValidationError(template="a", version=1, line=1, reason="unknown key"),),
        unvalidated=("a.b",),
    )

    out = ValidateOut.of(result)

    assert out.unvalidated == ["a.b"]
    assert out.errors[0].reason == "unknown key"


def test_validate_out_of_a_clean_result() -> None:
    out = ValidateOut.of(ValidationResult())

    assert out.errors == []
    assert out.unvalidated == []


def test_an_unpinned_call_and_a_following_caller_render_their_own_shapes() -> None:
    stored = TemplateVersion(
        name="leaf",
        version=1,
        yaml="name: leaf\nversion: 1\nsteps: []\n",
        hash="sha",
        calls=(TemplateCallRef(name="child", version=None),),
        created_at=AT,
    )
    detail = TemplateVersionDetail(
        template=stored,
        called_by=(TemplateCaller(name="root", version=2, pinned=False),),
        inputs=(),
    )

    out = TemplateVersionOut.of(detail)

    assert out.model_dump()["calls"] == [{"name": "child", "version": None}]
    assert out.model_dump()["called_by"] == [{"name": "root", "version": 2, "pinned": False}]
