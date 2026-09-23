"""The one read pass a dispatch is judged by — and the only one it runs (AD-12, S6).

`preflight_initiative` and `dispatch_initiative` both call `validate_initiative`, so a
dispatch cannot succeed on a graph the pre-flight would have refused, and the pre-flight
cannot refuse something the dispatch would have allowed. Everything here reads; nothing
writes.

The order below is the order an Operator would ask the questions in, and each step stops
where the next one could not be asked: a file that did not parse has no repositories to
resolve, and a Template this instance has never stored has no version to pre-flight against.
`Validated` carries the pre-flight plus the four things only the write half needs from the
same pass — the resolved members, the entries, the resolved versions, and the hub.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from orchestrator.application.initiatives.epics import Epic, parse_epics, wavefront
from orchestrator.application.initiatives.model import (
    EpicPreflight,
    InitiativePreflight,
    InitiativeRequest,
    RepoRow,
)
from orchestrator.application.initiatives.plan import (
    CHECK_EPIC,
    EpicSpec,
    Member,
    base_dir_of,
    branch_lines,
    epic_preflight_request,
    latest_version,
    resolve_members,
    spec_folder_line,
    template_lines,
    wavefront_line,
)
from orchestrator.application.preflight.model import Line
from orchestrator.application.templates.reader import PlanReader
from orchestrator.application.use_cases.preflight import PreflightPorts, preflight_and_plan
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.errors import NotFound


@dataclass(frozen=True)
class Validated:
    """The pre-flight, plus what only the write half needs from the same one pass."""

    preflight: InitiativePreflight
    members: tuple[Member, ...] = ()
    epics: tuple[Epic, ...] = ()
    versions: dict[str, int] = field(default_factory=dict)
    project: Project | None = None
    hub: Repository | None = None


def validate_initiative(ports: PreflightPorts, req: InitiativeRequest) -> Validated:
    """Read the file, check the graph, resolve the repositories, pre-flight every epic."""
    project = ports.projects.get(req.project_id)
    if project is None:
        raise NotFound(f"no project {req.project_id}")
    hub = ports.repositories.get(req.repository_id)
    if hub is None:
        raise NotFound(f"no repository {req.repository_id}")
    parsed = parse_epics(read_epics(ports, req, project, hub))
    lines = list(parsed.lines) + template_lines(ports.templates, req.templates)
    if lines:
        return Validated(InitiativePreflight(slug=req.slug, lines=tuple(lines)))
    members, missing = resolve_members(
        parsed.epics,
        ports.repositories.list_by_project(req.project_id),
        project=project,
        work_dir=ports.work_dir,
        git=ports.git,
    )
    lines += missing
    lines += branch_lines(members)
    lines.append(wavefront_line(len(wavefront(parsed.epics)), ports.max_active_runs))
    versions = {name: latest_version(ports.templates, name) or 0 for name in req.templates}
    return Validated(
        preflight=InitiativePreflight(
            slug=req.slug,
            lines=tuple(lines),
            epics=tuple(_epic_preflight(ports, req, member, versions) for member in members),
            repos=_repo_rows(members),
            order=parsed.order,
        ),
        members=members,
        epics=parsed.epics,
        versions=versions,
        project=project,
        hub=hub,
    )


def read_epics(
    ports: PreflightPorts, req: InitiativeRequest, project: Project, hub: Repository
) -> str | None:
    """`{initiative_folder}/epics.yaml` off the hub's base branch, or `None`.

    Through `PlanReader`, the planner's own one door to `Git` — so the hub's base branch is
    resolved by the same `ls_remote` every other read of it uses, and a base branch the
    remote does not hold reads as "no file" rather than as a traceback.
    """
    reader = PlanReader(ports.git, base=base_dir_of(ports.work_dir, project, hub), url=hub.url)
    ref = reader.sha(req.base_branch)
    return None if ref is None else reader.read(ref, req.epics_path)


def _epic_preflight(
    ports: PreflightPorts, req: InitiativeRequest, member: Member, versions: dict[str, int]
) -> EpicPreflight:
    """One epic's own lines: its spec folder, plus the whole of the Run's pre-flight."""
    lines: list[Line] = []
    folder = spec_folder_line(member, ports.git)
    if folder is not None:
        lines.append(folder)
    spec = EpicSpec(
        project_id=req.project_id,
        template=req.epic_template,
        version=versions[req.epic_template],
        harness=req.harness,
        model=req.model,
    )
    result = preflight_and_plan(ports, epic_preflight_request(member, spec))
    lines += [_named(line, member.epic.id) for line in result.result.lines]
    return EpicPreflight(
        epic_id=member.epic.id,
        title=member.epic.title,
        repository_id=member.repository.id,
        repository_slug=member.repository.slug,
        branch=member.branch,
        working_branch=member.working_branch,
        depends_on=member.epic.depends_on,
        checkpoint=member.epic.checkpoint,
        lines=tuple(lines),
    )


def _named(line: Line, epic_id: str) -> Line:
    """One per-Run line, re-checked as this epic's.

    Without it a dozen `branch` lines all read as one Run's and the Operator cannot tell
    which epic refused — which is the whole difference between an initiative's pre-flight
    and a Run's.
    """
    return Line(
        check=f"{CHECK_EPIC} {epic_id}: {line.check}",
        status=line.status,
        text=line.text,
        fix=line.fix,
    )


def _repo_rows(members: tuple[Member, ...]) -> tuple[RepoRow, ...]:
    """One row per repository the initiative touches, in first-mention order."""
    rows: dict[UUID, RepoRow] = {}
    for member in members:
        rows.setdefault(
            member.repository.id,
            RepoRow(
                repository_id=member.repository.id,
                slug=member.repository.slug,
                branch=member.branch,
                default_branch=member.repository.default_branch,
                remote_holds=member.remote_holds,
            ),
        )
    return tuple(rows.values())
