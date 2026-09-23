"""Everything a dispatch has to be sure of before it writes the first Run (AD-12, AD-14).

Pure: ports in, `Line`s out, nothing written. Five questions, in the order an Operator would
ask them:

1. **Does each `repo` name a Repository of this Project?** Matched on the slug exactly, then
   on the slug the entry's own text would produce (`repo_slug`), so `epics.yaml` may say
   `web-client`, `web-client.git` or a whole clone URL and mean the same row. A miss names
   the entry, because "repository not found" without an id is not actionable.
2. **Is the integration branch something a Run may push?** `git.push` refuses a branch equal
   to `repository.default_branch` at run time (AD-14), and a merge Run pushes exactly the
   integration branch — so an initiative that names the default branch has no legal merge and
   is refused here, before any Run exists to fail on its last row.
3. **Does each epic's `spec_folder` exist in its own repository?** Looked for at the
   integration branch when the origin already holds it, else at the repository's default
   branch — the planner's own fallback idiom, so a folder that only exists on a branch
   already opened is found and a folder nobody has written yet is not.
4. **Would each epic Run actually plan?** The whole of `preflight_and_plan`, per epic, at the
   template version this dispatch would use. This is the expensive half and the honest one:
   an initiative that passed its own checks and then failed at `POST /runs` would have been
   refused after some of its Runs already existed.
5. **How wide is wave 0, against this instance's cap?** One line, always present.

The base clone path is rebuilt here rather than imported from `use_cases/preflight.py`,
whose `_base_dir` is private: AD-14 states it once (`{work_dir}/{project}/{repo}/base`) and
two readings of that one sentence cannot drift the way two implementations of two sentences
could.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from orchestrator.application.initiatives.epics import Epic
from orchestrator.application.preflight.model import Line, PreflightRequest
from orchestrator.application.templates.reader import PlanReader
from orchestrator.application.use_cases.clone_check import BASE_DIRECTORY
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import Repository, repo_slug
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.templates import TemplateVersionRepository

#: What separates the segments of a repository-relative path. The same rule
#: `templates/lists.py` states for a list file's own folder.
EPICS_PATH_SEPARATOR = "/"

#: The check names this module's lines carry.
CHECK_REPOS = "initiative repositories"
CHECK_BRANCH = "initiative branch"
CHECK_SPEC = "initiative spec folder"
CHECK_TEMPLATE = "initiative template"
CHECK_WAVEFRONT = "initiative wavefront"
CHECK_EPIC = "initiative epic"

#: The refusals, each naming what the Operator has to change.
NO_SUCH_REPO = "epic {item}: repo {repo!r} is not a repository of this project"
BRANCH_IS_DEFAULT = "repo {item}: integration branch {branch!r} is the default branch"
NO_SPEC_FOLDER = "epic {item}: spec folder {folder!r} is not in {repo} at {ref}"
NO_TEMPLATE = "template {item!r} is not stored"

#: The line AD-12 asks for, warn when the wave is wider than the instance can run at once.
WAVEFRONT = "initiative wavefront is {n} parallel runs; MAX_ACTIVE_RUNS is {m}"

#: How each epic's working branch is named off its repository's integration branch. The
#: planner then allocates the first free ordinal of it (AD-7), which is what a merge Run's
#: `from_branch` ends up being.
WORKING_BRANCH = "{branch}-{epic_id}"

#: What `epic@1` declares beyond the four every Template binds. `done_checkpoint` is a
#: string because the DSL has no bool input (S5): `"true"` stops, `""` does not.
BRANCH_INPUT = "branch"
SPEC_FOLDER_INPUT = "spec_folder"
DONE_CHECKPOINT_INPUT = "done_checkpoint"
CHECKPOINT_ON = "true"
CHECKPOINT_OFF = ""

#: What `merge@1` declares beyond `project`/`repository`/`base_branch`.
DEVELOP_BRANCH_INPUT = "develop_branch"
FROM_BRANCH_INPUT = "from_branch"

#: `golive@1`'s one optional, documentary input.
HOLDS_INPUT = "holds"


@dataclass(frozen=True)
class Member:
    """One epic, bound to the Repository it runs against and the branch it lands on."""

    epic: Epic
    repository: Repository
    #: The repository's integration branch — every epic of that repository shares it.
    branch: str
    #: Whether the origin already holds that branch. `False` means dispatch creates it.
    remote_holds: bool
    #: The commit the branch would be created at, when the origin does not hold it yet.
    at_ref: str
    #: `{work_dir}/{project}/{repo}/base` — this member's own base clone (AD-14).
    base_dir: Path

    @property
    def working_branch(self) -> str:
        """The branch the epic Run declares — before AD-7 allocates its fresh ordinal."""
        return WORKING_BRANCH.format(branch=self.branch, epic_id=self.epic.id)

    @property
    def preflight_base(self) -> str:
        """Which branch an epic Run is pre-flighted from *before* the integration branch
        exists: the branch itself once the origin holds it, the repository's default branch
        until then. The planner's own list-file fallback, applied one level up."""
        return self.branch if self.remote_holds else self.repository.default_branch


def base_dir_of(work_dir: Path, project: Project, repository: Repository) -> Path:
    """`{work_dir}/{project.slug}/{repository.slug}/base` — AD-14's one sentence."""
    return work_dir / project.slug / repository.slug / BASE_DIRECTORY


def latest_version(templates: TemplateVersionRepository, name: str) -> int | None:
    """The highest version stored under a Template name, or `None` when none is.

    Latest at dispatch time, never a pinned number: the request names the templates
    (AD-7/AD-12), and an instance that has saved a newer `epic` is meant to dispatch that
    one. The same `max(list_versions(name))` `use_cases/templates.py::graph_latest` and
    `validate_latest` already answer with.
    """
    versions = templates.list_versions(name)
    return max(versions) if versions else None


def template_lines(templates: TemplateVersionRepository, names: tuple[str, ...]) -> list[Line]:
    """A `fail` per requested Template this instance has never stored."""
    return [
        Line(check=CHECK_TEMPLATE, status="fail", text=NO_TEMPLATE.format(item=name))
        for name in names
        if latest_version(templates, name) is None
    ]


def resolve_members(
    epics: tuple[Epic, ...],
    repositories: list[Repository],
    *,
    project: Project,
    work_dir: Path,
    git: Git,
) -> tuple[tuple[Member, ...], list[Line]]:
    """Every epic bound to its Repository, plus a `fail` per entry that named none."""
    by_slug = {repository.slug: repository for repository in repositories}
    members: list[Member] = []
    lines: list[Line] = []
    readers: dict[str, PlanReader] = {}
    for epic in epics:
        repository = by_slug.get(epic.repo) or by_slug.get(repo_slug(epic.repo))
        if repository is None:
            lines.append(
                Line(
                    check=CHECK_REPOS,
                    status="fail",
                    text=NO_SUCH_REPO.format(item=epic.id, repo=epic.repo),
                )
            )
            continue
        base_dir = base_dir_of(work_dir, project, repository)
        reader = readers.setdefault(
            repository.slug, PlanReader(git, base=base_dir, url=repository.url)
        )
        members.append(_member(epic, repository, base_dir, reader))
    return tuple(members), lines


def _member(epic: Epic, repository: Repository, base_dir: Path, reader: PlanReader) -> Member:
    """One resolved member: does the origin hold the branch, and where would it start?"""
    held = reader.sha(epic.branch)
    default_head = reader.sha(repository.default_branch)
    return Member(
        epic=epic,
        repository=repository,
        branch=epic.branch,
        remote_holds=held is not None,
        # the entry's own baseline wins; otherwise the default branch's head, and the branch
        # name itself when the clone cannot resolve one (the `fail` for that is the
        # repository's clone check, not this line's business)
        at_ref=epic.baseline_sha or default_head or repository.default_branch,
        base_dir=base_dir,
    )


def branch_lines(members: tuple[Member, ...]) -> list[Line]:
    """A `fail` per repository whose integration branch is its default branch (AD-14)."""
    seen: set[str] = set()
    lines: list[Line] = []
    for member in members:
        if member.repository.slug in seen:
            continue
        seen.add(member.repository.slug)
        if member.branch == member.repository.default_branch:
            lines.append(
                Line(
                    check=CHECK_BRANCH,
                    status="fail",
                    text=BRANCH_IS_DEFAULT.format(
                        item=member.repository.slug, branch=member.branch
                    ),
                )
            )
    return lines


def spec_folder_line(member: Member, git: Git) -> Line | None:
    """A `fail` when the epic's `spec_folder` is in neither candidate ref, else `None`."""
    reader = PlanReader(git, base=member.base_dir, url=member.repository.url)
    ref_branch = member.preflight_base
    ref = reader.sha(ref_branch)
    if ref is not None and reader.listing(ref, member.epic.spec_folder):
        return None
    return Line(
        check=CHECK_SPEC,
        status="fail",
        text=NO_SPEC_FOLDER.format(
            item=member.epic.id,
            folder=member.epic.spec_folder,
            repo=member.repository.slug,
            ref=ref_branch,
        ),
    )


def wavefront_line(count: int, max_active_runs: int) -> Line:
    """AD-12's own sentence: how many Runs start at once, against the instance's cap."""
    return Line(
        check=CHECK_WAVEFRONT,
        status="warn" if count > max_active_runs else "ok",
        text=WAVEFRONT.format(n=count, m=max_active_runs),
    )


def epic_inputs(member: Member) -> dict[str, str]:
    """What an `epic` Run binds beyond the four every Template gets.

    `epic@1` also declares an optional `epic` input of type `item`. It stays unbound: a Run's
    `inputs` map binds strings the Operator submitted, an `item` is what a `for_each` frame
    hands a callee, and `plan_run`'s root scope has no frame to take one from — an optional
    input nobody bound is simply not in scope, which is the DSL's own answer.
    """
    return {
        BRANCH_INPUT: member.working_branch,
        SPEC_FOLDER_INPUT: member.epic.spec_folder,
        DONE_CHECKPOINT_INPUT: CHECKPOINT_ON if member.epic.blocks_merge else CHECKPOINT_OFF,
    }


@dataclass(frozen=True)
class EpicSpec:
    """What every epic Run of one dispatch has in common: the Project, the resolved
    Template Version, and the agent choices. One object rather than five keyword arguments,
    because the five always travel together (`PLR0913`, and `AttemptRepository.mark_started`
    is this codebase's own precedent for the move)."""

    project_id: UUID
    template: str
    version: int
    harness: str | None = None
    model: str | None = None


def epic_preflight_request(member: Member, spec: EpicSpec) -> PreflightRequest:
    """The would-be epic Run, as pre-flight sees it before anything has been created."""
    return PreflightRequest(
        template_name=spec.template,
        template_version=spec.version,
        project_id=spec.project_id,
        repository_id=member.repository.id,
        base_branch=member.preflight_base,
        inputs=dict(epic_inputs(member)),
        harness=spec.harness,
        model=spec.model,
    )
