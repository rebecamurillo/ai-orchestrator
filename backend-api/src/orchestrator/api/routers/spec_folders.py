"""`POST /api/v1/spec-folders/validate` — the launch check, before the push (AD-35).

It calls the two pure functions of `application/spec_folder.py` and nothing else, so what it
answers is what the plan reports after the push. A defect is data: 200 with findings.
"""

from __future__ import annotations

from fastapi import APIRouter

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
    ProblemError,
    finding_error,
)
from orchestrator.api.schemas.spec_folders import SpecFolderCheckOut, SpecFolderIn
from orchestrator.application import findings
from orchestrator.application.spec_folder import check_spec_folder, check_spec_md

router = APIRouter(tags=["spec-folders"])


# declared, or FastAPI publishes its own `HTTPValidationError` for the 422
OVERSIZED = {
    "model": ProblemDetail,
    "description": "More files or bytes than the limits allow, or an unsafe path.",
    "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
}


@router.post(
    "/spec-folders/validate",
    response_model=SpecFolderCheckOut,
    responses={HTTP_UNPROCESSABLE_CONTENT: OVERSIZED},
)
def validate_spec_folder(payload: SpecFolderIn) -> SpecFolderCheckOut:
    found = [
        finding_error(reason=e.reason, line=e.line, path=e.file)
        for e in check_spec_folder(payload.files)
    ]
    code = findings.REFUSAL_SPEC_MD_MISSING
    found += [
        ProblemError(reason=e.reason, path=e.file, code=code, guide=findings.guide_id(code))
        for e in check_spec_md(payload.files)
    ]
    return SpecFolderCheckOut(findings=found)
