"""`init_repository` (SPEC CAP-10, FR-30, AD-16): the Repository row's own action.

*Initialise repository* is `create_run` (4.4) given one fixed template — `repo-init` v1, on
`repository.default_branch`, with no harness (the plan has no `agent` step, and
`checks.py::harness_line` already answers `skip` for one, so nothing here has to special-case
that check). What this module adds is the two refusals only this feature makes: a Repository
whose last clone check `failed` cannot be initialised (the check is what would prove the
Repository is even reachable), and a Repository that already has a non-terminal `repo-init`
Run cannot be given a second one racing it for the same `chore/bmad-init` branch. Both are
declared narrower than pre-flight's own lines: pre-flight would happily plan a second
`repo-init` Run and let the repository lock (AD-12) queue it behind the first, which is
correct for two *different* Templates but wrong for two copies of this one.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
    CreateRunResult,
    create_run,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict, NotFound

#: The shipped Template this action always starts (AD-16). A later version never applies:
#: the brief is explicit that this is `repo-init@1`, not "the latest repo-init".
TEMPLATE_NAME = "repo-init"
TEMPLATE_VERSION = 1

#: `repo-init` has no `agent` step, so it accrues no gateway spend; `0` is a real budget, not
#: a placeholder one, and is unread by anything in this epic (`create_run`'s own docstring).
NO_BUDGET = Decimal("0")

CLONE_CHECK_FAILED = "clone check failed: run the clone check again before initialising"
ALREADY_RUNNING = "initialisation already running: {run_id}"


def init_repository(ports: CreateRunPorts, repository_id: UUID) -> CreateRunResult:
    """Start a `repo-init@1` Run on this Repository, refusing what only this action refuses."""
    repository = ports.preflight.repositories.get(repository_id)
    if repository is None:
        raise NotFound(f"no repository {repository_id}")
    if repository.clone_check.status == "failed":
        raise Conflict(CLONE_CHECK_FAILED)
    running = _non_terminal_repo_init(ports, repository_id)
    if running is not None:
        raise Conflict(ALREADY_RUNNING.format(run_id=running.id))

    request = CreateRunRequest(
        template_name=TEMPLATE_NAME,
        template_version=TEMPLATE_VERSION,
        project_id=repository.project_id,
        repository_id=repository.id,
        base_branch=repository.default_branch,
        budget_usd=NO_BUDGET,
    )
    return create_run(ports, request)


def _non_terminal_repo_init(ports: CreateRunPorts, repository_id: UUID) -> Run | None:
    """The Repository's own unfinished `repo-init` Run, or `None` — every other Template on
    this Repository is pre-flight's own concern (the repository lock queues behind it)."""
    existing = ports.preflight.runs.list_by_repository_non_terminal(repository_id)
    return next((run for run in existing if run.template_name == TEMPLATE_NAME), None)
