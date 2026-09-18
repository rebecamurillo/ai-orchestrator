"""`GET /api/v1/runs/{run_id}/steps/{step_path}` (story 1-2): full detail for one step.

Returns the step's planned metadata, its `with_resolved` context, and every attempt
(newest first) with the dispatch prompt, retry prompt, extracted result and command.

The `step_path` parameter arrives URL-decoded by FastAPI — the web-client
`encodeURIComponent`s brackets before inserting into the URL (AD-15), and Starlette
decodes it back before handing it to this handler.

All git reads flow through the `Git` port on `RunViewPorts` (AD-1, AD-2).  The endpoint
writes no status (AD-8) and adds no new dependency function — it reuses `run_view_ports`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    Problem,
    ProblemDetail,
)
from orchestrator.api.providers import run_view_ports
from orchestrator.api.schemas.step_detail import AttemptDetailOut, StepDetailOut
from orchestrator.application.graph import STEP_TOKENS
from orchestrator.application.use_cases.run_view_types import RunViewPorts
from orchestrator.application.use_cases.step_detail import (
    _dispatch_prompt,
    _extract_result,
    _retry_prompt,
    step_detail,
)
from orchestrator.application.use_cases.terminal import Terminal
from orchestrator.application.use_cases.terminal import resume_command as _terminal_resume
from orchestrator.domain.errors import NotFound

router = APIRouter(tags=["runs"])

Ports = Annotated[RunViewPorts, Depends(run_view_ports)]

HTTP_NOT_FOUND = 404


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


BAD_ID_RESPONSE = _refusal("`run_id` does not parse as a UUID.")
REFUSALS: dict[int, object] = {
    HTTP_NOT_FOUND: _refusal("No run or step with those identifiers."),
    # Declared so FastAPI does not publish its own `HTTPValidationError` schema for the
    # path-parameter 422 — `test_projects_router.py` sweeps the whole document.
    HTTP_UNPROCESSABLE_CONTENT: BAD_ID_RESPONSE,
}


@router.get(
    "/runs/{run_id}/steps/{step_path}",
    response_model=StepDetailOut,
    summary="Read one step's full history and context",
    responses=REFUSALS,
)
def get_step_detail(
    run_id: UUID,
    step_path: str,
    ports: Ports,
) -> StepDetailOut:
    """Return one step's metadata and every attempt, newest first.

    Writes nothing; derives no status (AD-8).
    """
    try:
        run, step, attempts = step_detail(ports, run_id, step_path)
    except NotFound as exc:
        raise Problem(status=HTTP_NOT_FOUND, title=str(exc)) from exc

    worktree = Path(run.worktree_path) if run.worktree_path else None

    dispatch_prompt = _dispatch_prompt(step.with_resolved)
    retry_prompt_val = _retry_prompt(step.with_resolved)
    command = step.with_resolved.get("run")

    spec_folder = step.with_resolved.get("spec_folder")
    story_id = step.with_resolved.get("story_id")

    project = ports.projects.get(run.project_id)
    project_slug = project.slug if project else ""

    attempt_details = []
    for attempt in attempts:
        t: Terminal | None = (
            _terminal_resume(ports.terminal, run, step, attempt, project_slug=project_slug)
            if ports.terminal
            else None
        )
        attempt_details.append(
            AttemptDetailOut(
                id=attempt.id,
                n=attempt.n,
                status=attempt.status,
                token=STEP_TOKENS.get(attempt.status, attempt.status[:3].upper()),
                started_at=attempt.started_at,
                ended_at=attempt.ended_at,
                seconds=(
                    (attempt.ended_at - attempt.started_at).total_seconds()
                    if attempt.ended_at and attempt.started_at
                    else None
                ),
                harness=attempt.harness,
                model=attempt.model,
                session_id=attempt.session_id,
                exit_code=attempt.exit_code,
                cost_usd=attempt.cost_usd,
                cost_provisional=attempt.cost_provisional,
                tokens_in=attempt.tokens_in,
                tokens_out=attempt.tokens_out,
                dispatch_prompt=dispatch_prompt,
                retry_prompt=retry_prompt_val,
                result=_extract_result(
                    ports.git,
                    worktree,
                    attempt.end_sha,
                    str(spec_folder) if spec_folder else None,
                    str(story_id) if story_id else None,
                ),
                command=str(command) if command is not None else None,
                resume_command=t.command if t else None,
                session_lifetime_ends_at=t.session_lifetime_ends_at if t else None,
            )
        )

    return StepDetailOut(
        seq=step.seq,
        path=step.path,
        label=step.label,
        kind=step.kind,
        gate=step.gate,
        status=step.status,
        token=STEP_TOKENS.get(step.status, step.status[:3].upper()),
        reason=step.reason,
        with_resolved=step.with_resolved,
        attempts=attempt_details,
    )
