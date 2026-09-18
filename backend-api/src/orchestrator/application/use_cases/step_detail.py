"""Step-run detail use case (story 1-2, AD-15).

Returns one step's full data — the step entity and its attempts, newest first — for the
`GET /runs/{run_id}/steps/{step_path}` endpoint.  Three private helpers derive the
presentation fields the router needs to build `AttemptDetailOut`:

- `_dispatch_prompt` — the harness dispatch sentence from `with_resolved`, or `None`.
- `_retry_prompt` — the retry prompt declared in the Template's `retry.prompt`, or `None`.
- `_extract_result` — the `## Auto Run Result` section from the spec file at `end_sha`.

All git access flows through the `Git` port on `RunViewPorts`.  When the port is `None`
or the run has no `worktree_path`, result extraction short-circuits to `None` without
touching the filesystem (AD-1, AD-2).

This module is `application/`-layer: it may import `domain/` entities, ports and errors,
and `application/steps/` helpers, but never `fastapi`, `sqlalchemy`, or any I/O adapter.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from orchestrator.application.steps.agent import compose_prompt
from orchestrator.application.templates.agent_row import RETRY_KEY
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.git import Git


def _dispatch_prompt(with_resolved: Mapping[str, Any]) -> str | None:
    """The dispatch sentence the harness received, derived from `with_resolved`.

    - A skill dispatch calls `compose_prompt` with no resume signal and no previous attempt,
      which returns the base sentence without any operator-answer suffix (AD-14, FR-14).
    - A prompt dispatch returns the `prompt` key verbatim.
    - Shell and other kinds have neither, so `None`.
    """
    if with_resolved.get("skill"):
        return compose_prompt(with_resolved, None, None)
    prompt = with_resolved.get("prompt")
    if prompt:
        return str(prompt)
    return None


def _retry_prompt(with_resolved: Mapping[str, Any]) -> str | None:
    """The retry prompt declared in the Template's `retry.prompt`, or `None` when absent.

    The `retry` key is a dict with `max`, `prompt`, and `resume_session` sub-keys
    (see `application/templates/agent_row.py::RETRY_KEY`).
    """
    retry = with_resolved.get(RETRY_KEY)
    if not retry or not isinstance(retry, dict):
        return None
    prompt = retry.get("prompt")
    return str(prompt) if prompt else None


def _extract_result(
    git: Git | None,
    worktree: Path | None,
    end_sha: str | None,
    spec_folder: str | None,
    story_id: str | None,
) -> str | None:
    """The `## Auto Run Result` section from the spec file at `end_sha`, or `None`.

    Returns `None` when:
    - `git` is `None` (port not wired)
    - `worktree` is `None` (Run has no worktree path)
    - `end_sha` is `None` (attempt still running)
    - `spec_folder` or `story_id` is absent from `with_resolved`
    - The story file is not found under `{spec_folder}/stories/`
    - The file does not exist at `end_sha` (GC'd or never written)
    - The `## Auto Run Result` heading is absent from the file
    """
    if git is None or worktree is None or end_sha is None:
        return None
    if not spec_folder or not story_id:
        return None

    stories_prefix = f"{spec_folder}/stories"
    paths = git.list_files(worktree, end_sha, stories_prefix)
    spec_path = next(
        (p for p in paths if p.split("/")[-1].startswith(f"{story_id}-")),
        None,
    )
    if spec_path is None:
        return None

    content = git.read_file(worktree, end_sha, spec_path)
    if content is None:
        return None

    lines = content.splitlines()
    HEADING = "## Auto Run Result"
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == HEADING)
    except StopIteration:
        return None

    result_lines: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        result_lines.append(line)

    return "\n".join(result_lines).strip() or None


def step_detail(
    ports: Any,
    run_id: UUID,
    step_path: str,
) -> tuple[Run, StepRun, list[Attempt]]:
    """Fetch the run, one step, and its attempts, newest first.

    Raises `NotFound` when the run does not exist or the path is not a step in it.
    Returns the `Run` so the caller does not need a second repository lookup to read
    `worktree_path` for result extraction.

    `ports` is typed as `Any` to avoid a circular import between `application/` and
    `application/use_cases/run_view_types.py`; at runtime it is always a `RunViewPorts`.
    """
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"run {run_id} not found")

    steps = ports.steps.list_for_run(run_id)
    step = next((s for s in steps if s.path == step_path), None)
    if step is None:
        raise NotFound(f"step {step_path!r} not found in run {run_id}")

    attempts = sorted(
        ports.attempts.list_for_row(step.id),
        key=lambda a: a.n,
        reverse=True,
    )
    return run, step, attempts
