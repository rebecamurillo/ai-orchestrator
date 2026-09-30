"""`embedded_runs` (SPEC CAP-10, FR-30, UX-DR12): the **RUNS ON THIS PROJECT** list, and the
one row `ProjectRead` needs to say which Run a Repository row's own action is about.

`GET /projects/{id}` embeds this the same way it already embeds `repositories` — a Project
read is one screen (`use_cases.embedded_repositories`), and a Repository row's *Initialise
repository* state and the record row it links to are both read off this one list rather than
a second request the Projects screen would have to make.

`ProjectRunSummary` carries three pieces of context no stored column answers on its own:

- **`current_step_label`** — the label the Operator would point at right now: the parked
  row while one is parked, the running row while one is, the next queued row otherwise, and
  the last row that was ever touched once nothing is left to do. It is a *label*
  (`checkout`, `install`), never a path, because record rows and cards show labels
  (`RecordRow.astro`'s own contract).
- **`reason`** — the sentence a `failed` or `cancelled` Run's row states beside its token.
  A `failed` Run always has an `error` row (`_fail`, `application/use_cases/
  apply_step_result.py`, is the only way a Run reaches `failed`, and it never runs without
  routing through one) and that row's own `reason` is what the Operator already reads on the
  Steps table; a `cancelled` Run clears `park_reason` (AD-8's `clear_park`), so its
  reason is the one fixed sentence `signal_run` always writes for it
  (`application/rules/signals.py::VALID["cancel"].text`) rather than a read this module
  would otherwise have to make of the gate record just to recover the same six words.
- **`is_init`** — whether this is the Repository's own *Initialise repository* Run. The
  fact is a comparison against `INIT_TEMPLATE` (AD-20), and it is made here so the screen
  reads a boolean instead of testing a Template's name (Operator decision 2026-09-30: no
  template name hardcoded in product code).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.repositories import RunRepository, StepRunRepository
from orchestrator.domain.statuses import RunStatus

#: How many Runs the Project screen shows, newest first (the brief's own bound).
EMBED_LIMIT = 20

#: The token `StatusToken.astro` renders (spine "UI tokens"). A Run never reads `SKP`.
Token = str

#: `signal_run`'s own fixed sentence for a cancel (`application/rules/signals.py::VALID`) —
#: repeated here as a literal, not imported, because reading a Run's gate record just to
#: recover six words `signal_run` writes unconditionally would be a second I/O port
#: (`GateRecordRepository`) for a sentence that is already this stable and this public.
CANCELLED_REASON = "cancelled by the operator"

_TOKENS: dict[RunStatus, Token] = {
    "queued": "QUE",
    "running": "RUN",
    "done": "DON",
    "failed": "ERR",
    "cancelled": "CAN",
    # "needs_you" is resolved by `_token` itself: `BLK` or `CHK` off `park_kind`.
}


@dataclass(frozen=True)
class ProjectRunSummary:
    """One row of a Project's Runs list, and what a Repository row's own action reads."""

    run: Run
    token: Token
    current_step_label: str
    reason: str
    #: Whether this Run is the Repository's own *Initialise repository* Run — the
    #: configured `INIT_TEMPLATE` (AD-20) is what it was planned from. Answered here, off
    #: configuration, rather than by the screen testing the Template's name (Operator
    #: decision 2026-09-30: no template name hardcoded in product code).
    is_init: bool = False


def embedded_runs(
    runs: RunRepository | None,
    steps: StepRunRepository | None,
    project_id: UUID,
    init_template: str = "",
) -> list[ProjectRunSummary]:
    """The Project's own Runs list, the way `embedded_repositories` (`use_cases/projects.py`)
    reads its Repositories: `[]` when either port is unwired, never a stale placeholder.

    `init_template` is `Settings.init_template` (AD-20); `""` marks no Run as an init Run,
    the same "not wired" tolerance the ports above take.
    """
    if runs is None or steps is None:
        return []
    stored = runs.list(project_id=project_id)[:EMBED_LIMIT]
    steps_by_run = {run.id: steps.list_for_run(run.id) for run in stored}
    return _summaries(stored, steps_by_run, init_template)


def _summaries(
    runs: Sequence[Run], steps_by_run: dict[UUID, list[StepRun]], init_template: str = ""
) -> list[ProjectRunSummary]:
    """The pure half: given the Runs and their rows, the label and the reason for each."""
    return [
        ProjectRunSummary(
            run=run,
            token=_token(run),
            current_step_label=_current_step_label(run, steps_by_run.get(run.id, [])),
            reason=_terminal_reason(run, steps_by_run.get(run.id, [])),
            is_init=bool(init_template) and run.template_name == init_template,
        )
        for run in runs
    ]


def _token(run: Run) -> Token:
    """The UI status token (spine "UI tokens"): stored status, or `park_kind` while parked."""
    if run.status == "needs_you":
        return "CHK" if run.park_kind == "checkpoint" else "BLK"
    return _TOKENS[run.status]


def _current_step_label(run: Run, steps: Sequence[StepRun]) -> str:
    """The row the Operator would point at right now, or the last one touched."""
    if not steps:
        return ""
    if run.park_path is not None:
        parked = next((row for row in steps if row.path == run.park_path), None)
        if parked is not None:
            return parked.label
    running = next((row for row in steps if row.status == "running"), None)
    if running is not None:
        return running.label
    queued = next((row for row in steps if row.status == "queued"), None)
    if queued is not None:
        return queued.label
    # Nothing is running, queued or parked: every row is `planned` (nothing started yet) or
    # this Run is terminal. `steps` is ordered by `seq` (`StepRunRepository.list_for_run`),
    # so the last non-`planned` row is the last one touched, and the first row otherwise.
    touched = [row for row in steps if row.status != "planned"]
    return touched[-1].label if touched else steps[0].label


def _terminal_reason(run: Run, steps: Sequence[StepRun]) -> str:
    """The sentence a `failed` or `cancelled` Run's row states beside its token; `""` for
    every other status, including `needs_you` (its own `park_reason` is that Question)."""
    if run.status == "failed":
        errored = next((row for row in steps if row.status == "error"), None)
        return errored.reason if errored is not None and errored.reason else ""
    if run.status == "cancelled":
        return CANCELLED_REASON
    return ""
