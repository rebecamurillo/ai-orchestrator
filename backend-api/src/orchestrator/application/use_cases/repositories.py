"""`init_repository` (SPEC CAP-10, FR-30, AD-16): the Repository row's own action.

*Initialise repository* is `create_run` (4.4) given the one Template this instance is
configured to initialise with (`Settings.init_template`, AD-20), on
`repository.default_branch`, with no harness budget — the shipped exemplar's plan has no
`agent` step, and `checks.py::harness_line` already answers `skip` for one, so nothing here
has to special-case that check. The name is *configuration*, never a constant: which
Template initialises a repository is an instance's choice, and the shipped file is an
exemplar (Operator decision 2026-09-30: no template name hardcoded in product code). The
version is not configuration at all — the latest stored version of the configured name is
resolved at dispatch (AD-7, AD-15).

What this module adds is the two refusals only this feature makes: a Repository whose last
clone check `failed` cannot be initialised (the check is what would prove the Repository is
even reachable), and a Repository that already has a non-terminal Run of that same Template
cannot be given a second one racing it for the same branch. Both are declared narrower than
pre-flight's own lines: pre-flight would happily plan a second initialisation Run and let
the repository lock (AD-12) queue it behind the first, which is correct for two *different*
Templates but wrong for two copies of this one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
    CreateRunResult,
    create_run,
)
from orchestrator.application.use_cases.templates import latest_version
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict, NotFound

#: The initialisation plan's one `agent` row spends nothing on the `fake` harness and a
#: real one is capped at this figure, so `0` is a real budget, not a placeholder one.
NO_BUDGET = Decimal("0")

CLONE_CHECK_FAILED = "clone check failed: run the clone check again before initialising"
ALREADY_RUNNING = "initialisation already running: {run_id}"


@dataclass(frozen=True)
class InitRepositoryPorts:
    """`create_run`'s own ports, plus the one thing only this action needs to be told."""

    create_run: CreateRunPorts
    #: `Settings.init_template` (AD-20) — which stored Template this instance initialises a
    #: Repository with, read once by the composition root. A name; `latest_version` resolves
    #: it against the store at dispatch.
    template_name: str


def init_repository(
    ports: InitRepositoryPorts, repository_id: UUID, harness: str | None = None
) -> CreateRunResult:
    """Start the configured initialisation Template on this Repository's default branch,
    refusing what only this action refuses. `harness` is the Operator's override for the
    Template's `agent` rows; `None` leaves the choice to `create_run`'s own default (AD-10).
    """
    repository = ports.create_run.preflight.repositories.get(repository_id)
    if repository is None:
        raise NotFound(f"no repository {repository_id}")
    if repository.clone_check.status == "failed":
        raise Conflict(CLONE_CHECK_FAILED)
    running = _non_terminal_init(ports, repository_id)
    if running is not None:
        raise Conflict(ALREADY_RUNNING.format(run_id=running.id))

    version = latest_version(ports.create_run.preflight.templates, ports.template_name)
    request = CreateRunRequest(
        template_name=ports.template_name,
        template_version=version,
        project_id=repository.project_id,
        repository_id=repository.id,
        base_branch=repository.default_branch,
        budget_usd=NO_BUDGET,
        harness=harness,
    )
    return create_run(ports.create_run, request)


def _non_terminal_init(ports: InitRepositoryPorts, repository_id: UUID) -> Run | None:
    """The Repository's own unfinished initialisation Run, or `None` — every other Template
    on this Repository is pre-flight's own concern (the repository lock queues behind it)."""
    existing = ports.create_run.preflight.runs.list_by_repository_non_terminal(repository_id)
    return next((run for run in existing if run.template_name == ports.template_name), None)
