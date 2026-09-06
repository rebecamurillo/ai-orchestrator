"""Pre-flight (SPEC CAP-3, FR-8): every reason a Run could fail at start, before it starts.

`run_preflight` resolves what it can — the Project, the Repository, the Template tree, the
Run's inputs — and calls `plan_run` (4.2) for *What will run* rather than reimplementing
any of it. Everything else is `application/preflight/checks.py` and `.../lists.py`,
composed here in FR-8's own order. Missing or unresolvable input never raises: a field
`run_preflight` cannot use just leaves its dependent lines `skip` (the brief's own rule),
so the New-workflow screen can call this on every keystroke.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.application.dto import ProjectSnapshot, RepositorySnapshot, RunInputs
from orchestrator.application.preflight import checks, lists
from orchestrator.application.preflight.checks import Context
from orchestrator.application.preflight.model import Line, PreflightRequest, PreflightResult
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import Plan, PlanError, ResolvedTree
from orchestrator.application.use_cases.clone_check import BASE_DIRECTORY
from orchestrator.application.use_cases.plan_run import resolve_tree
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.entities.template import TemplateRef
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.harnesses import HarnessRepository
from orchestrator.domain.ports.repositories import (
    ProjectRepository,
    RepositoryRepository,
    RunRepository,
)
from orchestrator.domain.ports.templates import TemplateVersionRepository

#: The harness `plan_run`'s substitution scope falls back to when the request names none —
#: `application/dto.py::RunInputs`'s own default. Pre-flight's harness *line* (checks.py)
#: reads `req.harness` directly and is unaffected by this.
DEFAULT_HARNESS = "claude"


@dataclass(frozen=True)
class PreflightPorts:
    """Everything `run_preflight` reaches the outside world through. Writes nothing."""

    git: Git
    templates: TemplateVersionRepository
    runs: RunRepository
    harnesses: HarnessRepository
    repositories: RepositoryRepository
    projects: ProjectRepository
    bmad_version: str
    max_active_runs: int
    #: The instance's clone root (AD-14, Settings.work_dir); the per-Repository base clone
    #: is `{work_dir}/{project.slug}/{repository.slug}/base`, computed once both resolve.
    work_dir: Path


@dataclass(frozen=True)
class _Resolved:
    """What `run_preflight` can resolve before it builds a `Plan` — the entities, not the
    request fields, so `_build_plan` and `Context` take one argument instead of four."""

    project: Project | None
    repository: Repository | None
    base_dir: Path
    tree: ResolvedTree | None
    tree_error: PlanError | None


def run_preflight(ports: PreflightPorts, req: PreflightRequest) -> PreflightResult:
    """Every FR-8 line, `start_allowed`, the queue note, and the rows the plan would persist."""
    resolved = _resolve(ports, req)
    plan, plan_error = _build_plan(ports, req, resolved)
    ctx = Context(
        git=ports.git,
        base_dir=resolved.base_dir,
        bmad_version=ports.bmad_version,
        max_active_runs=ports.max_active_runs,
        repository=resolved.repository,
        runs=ports.runs,
        harnesses=ports.harnesses,
        req=req,
        tree=resolved.tree,
        plan=plan,
        plan_error=plan_error,
    )
    lines = _lines(ctx)
    # The brief's formula ("no fail line and no plan_error") assumes a plan was built; a
    # request too incomplete to build one (AC5) has no fail line either, so `rows is not
    # None` is the third term that keeps "nothing to start" from reading as "start allowed".
    start_allowed = (
        plan is not None and plan_error is None and not any(line.status == "fail" for line in lines)
    )
    rows = plan.rows if plan is not None else None
    return PreflightResult(
        lines=tuple(lines),
        start_allowed=start_allowed,
        queue_note=checks.queue_note(ctx),
        rows=rows,
        plan_error=plan_error,
    )


def _resolve(ports: PreflightPorts, req: PreflightRequest) -> _Resolved:
    """The Project, the Repository, the per-Repository clone path, and the pinned tree."""
    project = ports.projects.get(req.project_id) if req.project_id else None
    repository = ports.repositories.get(req.repository_id) if req.repository_id else None
    base_dir = _base_dir(ports.work_dir, project, repository)
    tree, tree_error = _resolve_tree(ports.templates, req.template_name, req.template_version)
    return _Resolved(project, repository, base_dir, tree, tree_error)


def _lines(ctx: Context) -> list[Line]:
    """Every line, in FR-8's order."""
    lines: list[Line] = [checks.origin_reachable(ctx), checks.base_branch_line(ctx)]
    lines += checks.branch_lines(ctx)
    epics_line = lists.epics_yaml_line(ctx)
    if epics_line is not None:
        lines.append(epics_line)
    stories_lines, ids_by_path = lists.stories_yaml_lines(ctx)
    lines += stories_lines
    lines.append(checks.checkpoints_line(ctx))
    lines += lists.spec_md_lines(ctx)
    lines.append(checks.harness_line(ctx))
    lines.append(checks.method_version_line(ctx))
    lines.append(lists.existing_story_files_line(ctx, ids_by_path))
    lines.append(checks.clone_check_line(ctx))
    lines.append(checks.what_will_run_line(ctx))
    return lines


def _resolve_tree(
    templates: TemplateVersionRepository, name: str | None, version: int | None
) -> tuple[ResolvedTree | None, PlanError | None]:
    """The pinned tree, resolved once — `None, None` when the request does not name one."""
    if name is None or version is None:
        return None, None
    try:
        return resolve_tree(templates, TemplateRef(name=name, version=version)), None
    except PlanError as error:
        return None, error


def _build_plan(
    ports: PreflightPorts, req: PreflightRequest, resolved: _Resolved
) -> tuple[Plan | None, PlanError | None]:
    """*What will run*, or the `PlanError` naming why it could not be built."""
    if resolved.tree_error is not None:
        return None, resolved.tree_error
    inputs = _run_inputs(req, resolved.project, resolved.repository)
    if resolved.tree is None or inputs is None:
        return None, None
    try:
        plan = plan_run(
            resolved.tree,
            inputs,
            git=ports.git,
            base_dir=resolved.base_dir,
            bmad_version=ports.bmad_version,
        )
    except PlanError as error:
        return None, error
    return plan, None


def _base_dir(work_dir: Path, project: Project | None, repository: Repository | None) -> Path:
    """`{work_dir}/{project.slug}/{repository.slug}/base` (AD-14) once both resolve."""
    if project is None or repository is None:
        return work_dir
    return work_dir / project.slug / repository.slug / BASE_DIRECTORY


def _run_inputs(
    req: PreflightRequest, project: Project | None, repository: Repository | None
) -> RunInputs | None:
    """`None` when a field `plan_run` needs is missing — the request stays incomplete."""
    if project is None or repository is None or req.base_branch is None:
        return None
    return RunInputs(
        project=ProjectSnapshot(id=project.id, name=project.name, slug=project.slug),
        repository=RepositorySnapshot(
            id=repository.id,
            slug=repository.slug,
            url=repository.url,
            default_branch=repository.default_branch,
            install_command=repository.install_command or None,
            quality_gate_command=repository.quality_gate_command or None,
            unit_test_command=repository.unit_test_command or None,
            test_globs=repository.test_globs,
        ),
        base_branch=req.base_branch,
        values=req.inputs,
        harness=req.harness or DEFAULT_HARNESS,
        model=req.model,
        re_review_done=req.re_review_done,
    )
