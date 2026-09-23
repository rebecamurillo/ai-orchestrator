"""What a dispatch speaks in: one request, one pre-flight, one result (AD-12, S6).

Separate from `use_cases/dispatch_initiative.py` for the 400-line cap, and the split falls
where a reader would put it anyway: this module is the vocabulary — nothing here reaches a
port, and nothing here decides anything. `initiatives/validate.py` is the one read pass over
it, and the use case is the writes.

`InitiativeRequest` is one body for the pre-flight route and the dispatch route alike,
because the dispatch *is* the pre-flight plus the writes: two request shapes would be two
chances for the screen to check one thing and start another.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from orchestrator.application.initiatives.epics import EPICS_FILE
from orchestrator.application.initiatives.plan import EPICS_PATH_SEPARATOR
from orchestrator.application.preflight.model import Line
from orchestrator.domain.statuses import InitiativeRole

#: The Templates a dispatch instantiates when the request names none. Names, never versions:
#: the version is resolved to the latest stored at dispatch time (AD-7, AD-15).
DEFAULT_EPIC_TEMPLATE = "epic"
DEFAULT_MERGE_TEMPLATE = "merge"
DEFAULT_GOLIVE_TEMPLATE = "golive"

#: The three roles, as they are stored. Never derived from a template name (AD-12).
ROLE_EPIC: InitiativeRole = "epic"
ROLE_MERGE: InitiativeRole = "merge"
ROLE_GOLIVE: InitiativeRole = "golive"


@dataclass(frozen=True)
class InitiativeRequest:
    """`POST /initiatives` and `POST /initiatives/preflight`'s one body.

    `repository_id` is the **hub**: the repository whose `{initiative_folder}/epics.yaml`
    describes the work. It need not hold any of the epics itself.
    """

    project_id: UUID
    repository_id: UUID
    base_branch: str
    initiative_folder: str
    epic_template: str = DEFAULT_EPIC_TEMPLATE
    merge_template: str = DEFAULT_MERGE_TEMPLATE
    golive_template: str = DEFAULT_GOLIVE_TEMPLATE
    harness: str | None = None
    model: str | None = None
    #: The budget each **epic** Run is given. Merge and go-live Runs dispatch no agent, so
    #: they are created with none rather than with a share of one.
    budget_usd_per_epic: Decimal | None = None

    @property
    def slug(self) -> str:
        """The initiative's name: the basename of its folder, trailing separators ignored."""
        trimmed = self.initiative_folder.rstrip(EPICS_PATH_SEPARATOR)
        return trimmed.rpartition(EPICS_PATH_SEPARATOR)[2]

    @property
    def epics_path(self) -> str:
        """`{initiative_folder}/epics.yaml`, as the hub repository holds it."""
        trimmed = self.initiative_folder.rstrip(EPICS_PATH_SEPARATOR)
        return f"{trimmed}{EPICS_PATH_SEPARATOR}{EPICS_FILE}"

    @property
    def templates(self) -> tuple[str, str, str]:
        """The three Template names, in the order the members are created in."""
        return (self.epic_template, self.merge_template, self.golive_template)


@dataclass(frozen=True)
class EpicPreflight:
    """One would-be epic: where it lands, what it waits for, and every line about it."""

    epic_id: str
    title: str
    repository_id: UUID | None
    repository_slug: str | None
    branch: str
    working_branch: str | None
    depends_on: tuple[str, ...]
    checkpoint: str | None
    lines: tuple[Line, ...] = ()


@dataclass(frozen=True)
class RepoRow:
    """One repository the initiative touches, and the branch its epics merge into."""

    repository_id: UUID
    slug: str
    branch: str
    default_branch: str
    #: Whether the origin already holds the integration branch. `False` means the dispatch
    #: would create it (AD-14's `push_branch`, adopt-or-create).
    remote_holds: bool


@dataclass(frozen=True)
class InitiativePreflight:
    """What `POST /initiatives/preflight` answers, and what `dispatch` refuses on."""

    slug: str
    lines: tuple[Line, ...] = ()
    epics: tuple[EpicPreflight, ...] = ()
    repos: tuple[RepoRow, ...] = ()
    #: Epic ids in the order the Runs would be created — topological, file order breaking
    #: every tie. Empty exactly when a `fail` line says the graph could not be ordered.
    order: tuple[str, ...] = ()

    @property
    def all_lines(self) -> tuple[Line, ...]:
        """Every line, initiative-level first, then each epic's own."""
        return self.lines + tuple(line for epic in self.epics for line in epic.lines)

    @property
    def failing(self) -> tuple[Line, ...]:
        """Every line that refuses the dispatch — from anywhere in the initiative."""
        return tuple(line for line in self.all_lines if line.status == "fail")

    @property
    def start_allowed(self) -> bool:
        """Whether a dispatch of this request would be allowed to write anything."""
        return not self.failing


@dataclass(frozen=True)
class MemberRun:
    """One created Run, as the dispatch reports it."""

    run_id: UUID
    epic_id: str | None
    role: InitiativeRole
    repository_id: UUID
    after_run_ids: tuple[UUID, ...]
    #: The branch AD-7 allocated for this Run — set on an epic Run, so the merge Run created
    #: immediately after it can name it as `from_branch`. `None` on every other role.
    working_branch: str | None = None


@dataclass(frozen=True)
class DispatchResult:
    """`POST /initiatives`'s 201 body: the slug, and every Run that now exists."""

    slug: str
    members: tuple[MemberRun, ...]
    #: The epic ids whose Runs were enqueued — wave 0, the only Runs the engine has seen.
    started: tuple[str, ...]
