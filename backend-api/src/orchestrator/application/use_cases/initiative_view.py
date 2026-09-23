"""`GET /initiatives/{slug}`: the cross-repo DAG, read off the member Runs themselves.

There is no initiative table. AD-12 puts the whole graph on the Runs — `initiative`,
`initiative_role`, `initiative_epic_id`, and the `after_run_ids` edges that "nothing ever
clears … the retained edges are the durable record an initiative's DAG is rendered from" —
so this module is a projection and not a second source. Nothing here derives a status, a
role or a park: each is read from the stored Run exactly as AD-8's two writers left it.

**The integration branch is a fact about the epic Runs.** An epic Run's `base_branch` is its
repository's integration branch (that is what dispatch bound), so grouping the members by
repository and taking the first epic Run's base branch answers "which branch do this
repository's epics merge into" without storing it a second time. A repository that appears
only through the go-live Run — the hub, when it holds no epic of its own — has no integration
branch, and `None` says so rather than borrowing one.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from orchestrator.application.initiatives.model import ROLE_EPIC
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.repositories import RepositoryRepository, RunRepository
from orchestrator.domain.statuses import InitiativeRole, ParkKind, RunStatus

#: Where an epic Run's integration branch is bound, and where every Run's branch is.
BASE_BRANCH_INPUT = "base_branch"


@dataclass(frozen=True)
class InitiativeReadPorts:
    """What this read runs on. Writes nothing."""

    runs: RunRepository
    repositories: RepositoryRepository


@dataclass(frozen=True)
class MemberView:
    """One member Run, as the one-screen view renders it."""

    run_id: UUID
    epic_id: str | None
    role: InitiativeRole | None
    repository_id: UUID
    status: RunStatus
    park_kind: ParkKind | None
    park_reason: str | None
    after_run_ids: tuple[UUID, ...]
    template: str
    branch: str


@dataclass(frozen=True)
class RepoView:
    """One repository the initiative touches, and the branch its epics merge into."""

    repository_id: UUID
    slug: str
    url: str
    default_branch: str
    branch: str | None


@dataclass(frozen=True)
class InitiativeView:
    """The whole initiative on one screen: its repositories and its member Runs."""

    slug: str
    repos: tuple[RepoView, ...]
    members: tuple[MemberView, ...]


def get_initiative(ports: InitiativeReadPorts, slug: str) -> InitiativeView:
    """Every member Run of one initiative, grouped by the repositories they work in."""
    runs = ports.runs.list_by_initiative(slug)
    if not runs:
        raise NotFound(f"no initiative {slug!r}")
    # oldest first: the members read in the order the dispatch created them, which is the
    # topological order AD-12 creates in — `list_by_initiative` answers newest first, the
    # convention every Run list shares.
    ordered = list(reversed(runs))
    return InitiativeView(
        slug=slug,
        repos=_repos(ports, ordered),
        members=tuple(_member(run) for run in ordered),
    )


def _member(run: Run) -> MemberView:
    return MemberView(
        run_id=run.id,
        epic_id=run.initiative_epic_id,
        role=run.initiative_role,
        repository_id=run.repository_id,
        status=run.status,
        park_kind=run.park_kind,
        park_reason=run.park_reason,
        after_run_ids=run.after_run_ids,
        template=run.template_name,
        branch=_branch(run),
    )


def _branch(run: Run) -> str:
    """The branch this Run was created against — `RunSummaryOut`'s own reading of it."""
    return str(run.inputs.get(BASE_BRANCH_INPUT, ""))


def _repos(ports: InitiativeReadPorts, runs: list[Run]) -> tuple[RepoView, ...]:
    """One row per repository a member Run works in, in first-mention order."""
    branches: dict[UUID, str | None] = {}
    for run in runs:
        current = branches.setdefault(run.repository_id, None)
        if current is None and run.initiative_role == ROLE_EPIC:
            branches[run.repository_id] = _branch(run)
    rows: list[RepoView] = []
    for repository_id, branch in branches.items():
        stored = ports.repositories.get(repository_id)
        if stored is None:
            continue
        rows.append(
            RepoView(
                repository_id=repository_id,
                slug=stored.slug,
                url=stored.url,
                default_branch=stored.default_branch,
                branch=branch,
            )
        )
    return tuple(rows)
