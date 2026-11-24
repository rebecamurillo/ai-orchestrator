"""The conversation close check: the session's anchors outside the row's `writes` (AD-17
amended, R1).

Reads through the `Git` port only; the executor turns a non-empty answer into the
`protected_path` park.
"""

from __future__ import annotations

from collections.abc import Sequence

from orchestrator.application.rules import protected_paths
from orchestrator.application.use_cases import session_checks
from orchestrator.application.use_cases.walk_frame import INITIATIVE_FOLDER_INPUT, SLUG_INPUT
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.git import Git


def close_hits(
    git: Git, run: Run, rows: Sequence[StepRun], row: StepRun, attempts: Sequence[Attempt]
) -> tuple[str, ...]:
    """The paths `session_end` would list for this session, minus `run.accepted_paths` and
    what the row's `writes` declare inside the initiative folder."""
    changes = session_checks.session_changes(git, run, row, attempts)
    allowed = protected_paths.folder_patterns(
        protected_paths.declared(row.with_resolved),
        str(run.inputs.get(INITIATIVE_FOLDER_INPUT) or ""),
        str(run.inputs.get(SLUG_INPUT) or ""),
    )
    hits = protected_paths.check_interactive(
        changes, session_checks.run_anchors(run, rows), run.accepted_paths, allowed
    )
    return tuple(hit.path for hit in hits)
