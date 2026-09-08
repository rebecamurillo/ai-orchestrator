"""`start`: dispatch one readiness Run (SPEC CAP-8, AD-10, AD-16).

A harness is offered to the Operator only once it has proven itself on the fixture
Repository seeded under the built-in `readiness` Project (`harness_readiness_seed.py`).
`evaluate` (`harness_readiness_evaluate.py`) reads that Run back and is what actually
writes `enabled` — this module only ever creates the Run pre-flight would already allow,
with `skip_harness_check=True` so a harness that has never passed readiness can still run
the very readiness Run that would enable it (AD-10's own carried-forward flag).

Split into three modules — this one, `_evaluate.py`, `_seed.py` — because
`tests/unit/test_source_limits.py` caps every module at 400 lines and the three concerns
(dispatch, evaluation, start-up bootstrapping) do not share enough code to be worth the
length.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
    CreateRunResult,
    create_run,
)
from orchestrator.domain.entities.project import READINESS_PROJECT_SLUG
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.ports.repositories import RepositoryRepository

#: The one Repository the readiness fixture lives in, under the `readiness` Project.
READINESS_REPOSITORY_SLUG = "readiness-repo"
#: The Template every readiness Run is planned from (the brief's own words: `epic@1`).
READINESS_TEMPLATE_NAME = "epic"
READINESS_TEMPLATE_VERSION = 1
#: Where the fixture's kernel and its one story live, inside the readiness-repo clone.
READINESS_SPEC_FOLDER = "specs/readiness"
READINESS_BASE_BRANCH = "main"
#: The fixture's own one story (`fixtures/readiness-repo/specs/readiness/stories.yaml`).
READINESS_STORY_ID = "1"

#: The input key `_free_branch` and `evaluate` both read `run.inputs` by.
BRANCH_INPUT = "branch"
HARNESS_INPUT = "harness"


@dataclass(frozen=True)
class HarnessReadinessPorts:
    """Everything `start` reaches the outside world through.

    `create_run.preflight` already carries `runs`, `repositories` and `projects` — every
    read this function needs beyond the Decimal it is handed — so nothing here duplicates a
    port `create_run` already holds (the same reuse `CreateRunPorts`'s own docstring
    describes for `preflight`).
    """

    create_run: CreateRunPorts
    #: `Settings.readiness_budget_usd` (AD-20) — read once, by the composition root.
    budget_usd: Decimal


def start(ports: HarnessReadinessPorts, name: str) -> CreateRunResult:
    """Dispatch one `epic@1` readiness Run of `name` on the fixture Repository.

    `Conflict` (409) when a non-terminal readiness Run for `name` already exists — one
    harness readiness Run in flight at a time, so two `re-run readiness` clicks can never
    race each other onto the same branch.
    """
    preflight = ports.create_run.preflight
    project = preflight.projects.get_by_slug(READINESS_PROJECT_SLUG)
    if project is None:
        raise NotFound("the readiness Project is not seeded")
    repository = _readiness_repository(preflight.repositories, project.id)
    if repository is None:
        raise NotFound("the readiness Repository is not seeded")

    non_terminal = preflight.runs.list_by_repository_non_terminal(repository.id)
    if any(run.inputs.get(HARNESS_INPUT) == name for run in non_terminal):
        raise Conflict(f"a readiness run for {name!r} is already in progress")

    today = ports.create_run.clock.now().date()
    branch = _free_branch(non_terminal, name, today)
    request = CreateRunRequest(
        template_name=READINESS_TEMPLATE_NAME,
        template_version=READINESS_TEMPLATE_VERSION,
        project_id=project.id,
        repository_id=repository.id,
        base_branch=READINESS_BASE_BRANCH,
        budget_usd=ports.budget_usd,
        inputs={BRANCH_INPUT: branch, "spec_folder": READINESS_SPEC_FOLDER},
        harness=name,
    )
    return create_run(ports.create_run, request)


def _readiness_repository(
    repositories: RepositoryRepository, project_id: UUID
) -> Repository | None:
    for repository in repositories.list_by_project(project_id):
        if repository.slug == READINESS_REPOSITORY_SLUG:
            return repository
    return None


def _free_branch(non_terminal: list[Run], name: str, today: date) -> str:
    """`readiness/{name}/{date}`, suffixed `-2`, `-3`, ... past whatever a non-terminal Run
    for this harness already holds — a fresh `start` on a day the last one has not finished
    must never dispatch onto the branch that Run is still working on."""
    base = f"readiness/{name}/{today.isoformat()}"
    taken = {run.inputs.get(BRANCH_INPUT) for run in non_terminal}
    if base not in taken:
        return base
    suffix = 2
    while f"{base}-{suffix}" in taken:
        suffix += 1
    return f"{base}-{suffix}"
