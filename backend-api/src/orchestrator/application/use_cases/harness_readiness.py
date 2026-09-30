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

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID

from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
    CreateRunResult,
    create_run,
)
from orchestrator.application.use_cases.templates import latest_version
from orchestrator.domain.entities.harness import HARNESS_NAMES
from orchestrator.domain.entities.project import READINESS_PROJECT_SLUG
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.ports.repositories import RepositoryRepository

#: The model each harness's readiness Run binds when nothing overrides it — the committed
#: `READINESS_MODELS` contract, which `api/providers.py` passes in from
#: `Settings.readiness_models` on every real dispatch.
#:
#: One model per harness because a single value cannot be right: `codex` cannot run an
#: Anthropic model and `local` is pointed at the host's own model server. These three are
#: the cheapest route on each harness that can finish the fixture's one story, which is the
#: honest choice for a Run that exists to prove plumbing — session capture, tracing, spend
#: attribution — rather than to produce code.
#:
#: A default at all, rather than a required field, because a port built without one would
#: otherwise bind *no* model, which is the exact defect this mapping exists to remove.
DEFAULT_READINESS_MODELS: Mapping[str, str] = MappingProxyType(
    {"claude": "claude-sonnet-4-6", "codex": "gpt-5.4", "local": "local-coder"}
)

#: The one Repository the readiness fixture lives in, under the `readiness` Project.
READINESS_REPOSITORY_SLUG = "readiness-repo"
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
    #: `Settings.readiness_template` (AD-20) — which stored Template a readiness Run is
    #: planned from, read once by the composition root. A name, never `name@version`: the
    #: latest stored version of it is resolved at dispatch (AD-7, AD-15). Configuration
    #: rather than a constant, because which Template proves a harness is an instance's
    #: choice and the shipped one is an exemplar (Operator decision 2026-09-30: no
    #: template name hardcoded in product code).
    template_name: str
    #: `Settings.readiness_models` (AD-20), harness name → the model that harness's
    #: readiness Run binds. Defaults to the committed contract so a port built without it
    #: still binds something real; see `DEFAULT_READINESS_MODELS`.
    models: Mapping[str, str] = DEFAULT_READINESS_MODELS


def start(ports: HarnessReadinessPorts, name: str) -> CreateRunResult:
    """Dispatch one readiness Run of `name`, on the fixture Repository, from the configured
    Template at its latest stored version.

    `NotFound` (404) when `name` is not one of the three harnesses the image installs. That
    is checked first, and against `HARNESS_NAMES` rather than against the `harness` table:
    a missing row is how "never enabled" is stored, and this is the one endpoint that must
    work for a harness in exactly that state (AD-10). Checked *first* because every later
    statement treats the name as real — it becomes the branch `readiness/{name}/{date}` and
    then a `git ls-remote` for that branch, so an unrecognised name reached the remote and
    left a `GitError` as a 500 rather than a refusal naming the name.

    `Conflict` (409) when a non-terminal readiness Run for `name` already exists — one
    harness readiness Run in flight at a time, so two `re-run readiness` clicks can never
    race each other onto the same branch — and `Conflict` again when `ports.models` binds no
    model for `name`. That second refusal is checked second, before any seed is read,
    because a readiness Run that binds no model is the failure this whole path exists to
    avoid: `{{model}}` would resolve to the empty string and the harness would fall back to
    its own built-in default, which is not a route the operator's Gateway serves. 409 rather
    than 404 or 422: the name is real and the request is well formed, so what refuses is
    this instance's own state — that harness is not dispatchable as configured. `Settings`
    refuses a `READINESS_MODELS` that misses a harness at start-up, so this is the second
    of two gates, not the only one.
    """
    if name not in HARNESS_NAMES:
        raise NotFound(f"no harness named {name!r}")
    model = ports.models.get(name)
    if not model:
        raise Conflict(f"no readiness model is configured for {name!r} (READINESS_MODELS)")
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
        template_name=ports.template_name,
        template_version=latest_version(preflight.templates, ports.template_name),
        project_id=project.id,
        repository_id=repository.id,
        base_branch=READINESS_BASE_BRANCH,
        budget_usd=ports.budget_usd,
        inputs={BRANCH_INPUT: branch, "spec_folder": READINESS_SPEC_FOLDER},
        harness=name,
        model=model,
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
