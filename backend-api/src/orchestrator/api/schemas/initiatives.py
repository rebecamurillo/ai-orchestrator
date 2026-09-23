"""The HTTP shape of the four initiative routes (AD-12, AD-13; spine routes row).

`InitiativeIn` is one body for both `POST /initiatives/preflight` and `POST /initiatives`:
the dispatch is the pre-flight plus the writes, so two bodies would be two chances for the
screen to pre-flight one thing and start another. The three Template names are fields with
defaults rather than constants, because AD-12 says the templates a dispatch instantiates are
request inputs — the *version* is never one, and is resolved to the latest stored at dispatch
time by the use case.

`GET /initiatives/{slug}` answers a single object, like every other detail endpoint here;
`{items, next_cursor}` is the list convention and this read is not a list.

`InitiativeSignalIn`/`InitiativeSignalOut` (S8) are `POST /initiatives/{slug}/signals`'s own
body and result — AD-13's "the only signal surface above a single Run".
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from orchestrator.api.schemas.common import MoneyStr
from orchestrator.api.schemas.preflight import LineOut
from orchestrator.application.initiatives.model import (
    DEFAULT_EPIC_TEMPLATE,
    DEFAULT_GOLIVE_TEMPLATE,
    DEFAULT_MERGE_TEMPLATE,
    DispatchResult,
    EpicPreflight,
    InitiativePreflight,
    InitiativeRequest,
    MemberRun,
    RepoRow,
)
from orchestrator.application.use_cases.initiative_view import (
    InitiativeView,
    MemberView,
    RepoView,
)
from orchestrator.application.use_cases.signal_initiative import SignalInitiativeOutcome
from orchestrator.domain.statuses import InitiativeRole, ParkKind, RunStatus

#: The same `> 0` rule `POST /runs` puts on a budget; `null` leaves the epic Runs uncapped.
BudgetUsd = Annotated[MoneyStr, Field(gt=0)]


class InitiativeIn(BaseModel):
    """`POST /initiatives` and `POST /initiatives/preflight`'s one body."""

    project_id: UUID
    #: The **hub** repository: the one whose `{initiative_folder}/epics.yaml` describes the
    #: work. It need not hold any of the epics itself.
    repository_id: UUID
    base_branch: str
    initiative_folder: str
    epic_template: str = DEFAULT_EPIC_TEMPLATE
    merge_template: str = DEFAULT_MERGE_TEMPLATE
    golive_template: str = DEFAULT_GOLIVE_TEMPLATE
    harness: str | None = None
    model: str | None = None
    budget_usd_per_epic: BudgetUsd | None = None

    def as_request(self) -> InitiativeRequest:
        return InitiativeRequest(
            project_id=self.project_id,
            repository_id=self.repository_id,
            base_branch=self.base_branch,
            initiative_folder=self.initiative_folder,
            epic_template=self.epic_template,
            merge_template=self.merge_template,
            golive_template=self.golive_template,
            harness=self.harness,
            model=self.model,
            budget_usd_per_epic=self.budget_usd_per_epic,
        )


class EpicPreflightOut(BaseModel):
    """One would-be epic Run: where it lands, what it waits for, and its own lines."""

    epic_id: str
    title: str
    repository_id: UUID | None
    repository: str | None
    branch: str
    working_branch: str | None
    depends_on: list[str]
    checkpoint: str | None
    lines: list[LineOut]

    @classmethod
    def of(cls, epic: EpicPreflight) -> EpicPreflightOut:
        return cls(
            epic_id=epic.epic_id,
            title=epic.title,
            repository_id=epic.repository_id,
            repository=epic.repository_slug,
            branch=epic.branch,
            working_branch=epic.working_branch,
            depends_on=list(epic.depends_on),
            checkpoint=epic.checkpoint,
            lines=[LineOut.of(line) for line in epic.lines],
        )


class InitiativeRepoOut(BaseModel):
    """One repository the initiative touches, and the branch its epics merge into."""

    repository_id: UUID
    repository: str
    branch: str
    default_branch: str
    remote_holds_branch: bool

    @classmethod
    def of(cls, row: RepoRow) -> InitiativeRepoOut:
        return cls(
            repository_id=row.repository_id,
            repository=row.slug,
            branch=row.branch,
            default_branch=row.default_branch,
            remote_holds_branch=row.remote_holds,
        )


class InitiativePreflightOut(BaseModel):
    """`POST /initiatives/preflight`'s body: the DAG preview, the repo table, the lines."""

    slug: str
    start_allowed: bool
    lines: list[LineOut]
    repos: list[InitiativeRepoOut]
    epics: list[EpicPreflightOut]
    #: The epic ids in the order the Runs would be created — topological, file order
    #: breaking every tie. Empty exactly when a `fail` line says the graph has a cycle.
    order: list[str]

    @classmethod
    def of(cls, result: InitiativePreflight) -> InitiativePreflightOut:
        return cls(
            slug=result.slug,
            start_allowed=result.start_allowed,
            lines=[LineOut.of(line) for line in result.lines],
            repos=[InitiativeRepoOut.of(row) for row in result.repos],
            epics=[EpicPreflightOut.of(epic) for epic in result.epics],
            order=list(result.order),
        )


class MemberRunOut(BaseModel):
    """One Run a dispatch created."""

    run_id: UUID
    epic_id: str | None
    role: InitiativeRole
    repository_id: UUID
    after_run_ids: list[UUID]

    @classmethod
    def of(cls, member: MemberRun) -> MemberRunOut:
        return cls(
            run_id=member.run_id,
            epic_id=member.epic_id,
            role=member.role,
            repository_id=member.repository_id,
            after_run_ids=list(member.after_run_ids),
        )


class DispatchOut(BaseModel):
    """`POST /initiatives`'s 201 body: the slug, every Run created, and what started."""

    slug: str
    members: list[MemberRunOut]
    #: The epic ids whose Runs were enqueued — wave 0, the only Runs the engine has seen.
    started: list[str]

    @classmethod
    def of(cls, result: DispatchResult) -> DispatchOut:
        return cls(
            slug=result.slug,
            members=[MemberRunOut.of(member) for member in result.members],
            started=list(result.started),
        )


class InitiativeMemberOut(BaseModel):
    """One member Run on the one-screen view."""

    run_id: UUID
    epic_id: str | None
    role: InitiativeRole | None
    repository_id: UUID
    status: RunStatus
    park_kind: ParkKind | None
    park_reason: str | None
    after_run_ids: list[UUID]
    template: str
    branch: str

    @classmethod
    def of(cls, member: MemberView) -> InitiativeMemberOut:
        return cls(
            run_id=member.run_id,
            epic_id=member.epic_id,
            role=member.role,
            repository_id=member.repository_id,
            status=member.status,
            park_kind=member.park_kind,
            park_reason=member.park_reason,
            after_run_ids=list(member.after_run_ids),
            template=member.template,
            branch=member.branch,
        )


class InitiativeRepoViewOut(BaseModel):
    """One repository on the one-screen view."""

    repository_id: UUID
    repository: str
    url: str
    default_branch: str
    branch: str | None

    @classmethod
    def of(cls, repo: RepoView) -> InitiativeRepoViewOut:
        return cls(
            repository_id=repo.repository_id,
            repository=repo.slug,
            url=repo.url,
            default_branch=repo.default_branch,
            branch=repo.branch,
        )


class InitiativeOut(BaseModel):
    """`GET /initiatives/{slug}`'s body: the cross-repo DAG as one object."""

    slug: str
    repos: list[InitiativeRepoViewOut]
    members: list[InitiativeMemberOut]

    @classmethod
    def of(cls, view: InitiativeView) -> InitiativeOut:
        return cls(
            slug=view.slug,
            repos=[InitiativeRepoViewOut.of(repo) for repo in view.repos],
            members=[InitiativeMemberOut.of(member) for member in view.members],
        )


class InitiativeSignalIn(BaseModel):
    """`POST /initiatives/{slug}/signals`'s body (AD-13, S8): one signal kind, and nothing
    else — `cancel` is the only one this surface admits, and carries no payload of its own.
    `kind` is a plain `str` rather than `SignalKind`: any other value is well-formed at the
    schema level and refused by `signal_initiative` itself with the domain `Invalid` (422)
    the story asks for, the same way `signal_run.py::_check_mode` refuses an unknown `mode`.
    """

    kind: str


class InitiativeSignalOut(BaseModel):
    """`POST /initiatives/{slug}/signals`'s body: what was signalled, and what was already
    terminal and so left alone."""

    signalled: list[UUID]
    skipped: list[UUID]

    @classmethod
    def of(cls, outcome: SignalInitiativeOutcome) -> InitiativeSignalOut:
        return cls(signalled=list(outcome.signalled), skipped=list(outcome.skipped))
