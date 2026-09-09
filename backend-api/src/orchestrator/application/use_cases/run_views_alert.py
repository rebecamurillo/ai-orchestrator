"""The Run's own UI token and its `needs_you` Alert (SPEC CAP-12, CAP-2), split out of
`application/use_cases/run_views.py` on line count alone (`backend-api/AGENTS.md`'s 400-line
module limit — that module sat at exactly 400/400 before story 6-2's `row_kind`/
`checkpoint_story` fields, the same reason `application/steps/agent.py` split its own
Answer/archive logic into `agent_answer.py`). Re-exported back through `run_views.py` so
every existing import path still resolves; no test imports `_run_token`/`_attribution`/
`_alert` directly (they were module-private), so this move touches no assertion anywhere.

`checkpoint_story` (story 6-2) is the done-checkpoint's own summary line: `story {id} ·
{title} · {attempts} attempts · ${cost} · verify {done|skipped}`. None of those five facts
is stored as its own field anywhere — `title` in particular is never separately resolved:
the one place a Story's title reaches stored state is `templates/story.yaml`'s own
`commit-guard` row, whose `with:` block is `message: "story {{story.id}}: {{story.title}}
(orchestrator)"`. Reading it back out of that row's `with_resolved[COMMIT_MESSAGE_KEY]` is
the same kind of read `_bracket_index` and web-client's `misconfiguredFiles` already are:
a fact recovered from a string this system itself wrote in a fixed shape, not a new field
threaded through the planner for one summary line.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from uuid import UUID

from orchestrator.application.rules.frames import rows_in_frame, story_frame
from orchestrator.application.rules.protected_paths import park_record_payload
from orchestrator.application.steps import AGENT_KIND, COMMIT_KIND, COMMIT_MESSAGE_KEY, SHELL_KIND
from orchestrator.application.use_cases.run_view_types import Alert, Attribution, CheckpointStory
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import RunStatus

#: The Run's own UI token (Consistency Conventions — Status tokens): `BLK`/`CHK` while
#: parked, off `park_kind`, the fixed table otherwise. Duplicated from `application/
#: use_cases/project_runs.py::_token` and `application/graph.py::_run_token` — each reader's
#: own small pure function, the established precedent for a handful of lines (see
#: `project_runs.py`'s own docstring on `_current_step_label`).
_RUN_TOKENS: dict[RunStatus, str] = {
    "queued": "QUE",
    "running": "RUN",
    "done": "DON",
    "failed": "ERR",
    "cancelled": "CAN",
}

#: `templates/story.yaml`'s own commit message shape — the one place `story.title` reaches
#: stored state. A title containing " (orchestrator)" or ": " of its own would defeat this;
#: no shipped `stories.yaml` entry does, and `signal_run`'s own skip-story rewrite of this
#: same row (AD-13) reads it back the same way.
_TITLE_IN_MESSAGE = re.compile(r"^story\s+\S+:\s+(?P<title>.*)\s+\(orchestrator\)$")


def run_token(run: Run) -> str:
    if run.status == "needs_you":
        return "CHK" if run.park_kind == "checkpoint" else "BLK"
    return _RUN_TOKENS[run.status]


def build_alert(  # noqa: PLR0913 — one keyword per fact `checkpoint_story` needs, each named
    run: Run,
    attempt: Attempt | None,
    *,
    row_kind: str | None,
    rows: Sequence[StepRun],
    park_row: StepRun | None,
    attempts_by_row: Mapping[UUID, Sequence[Attempt]],
    records: Sequence[GateRecord] = (),
) -> Alert | None:
    if run.status != "needs_you":
        return None
    attribution = None if attempt is None else _attribution(attempt)
    checkpoint_story = None
    if run.park_kind == "checkpoint" and park_row is not None and row_kind != AGENT_KIND:
        checkpoint_story = _checkpoint_story(rows, attempts_by_row, park_row)
    return Alert(
        token=run_token(run),
        reason=run.park_reason,
        park_kind=run.park_kind,
        attribution=attribution,
        row_kind=row_kind,
        checkpoint_story=checkpoint_story,
        payload=park_record_payload(records, run),
    )


def _attribution(attempt: Attempt) -> Attribution:
    return Attribution(harness=attempt.harness, model=attempt.model, ended_at=attempt.ended_at)


def _checkpoint_story(
    rows: Sequence[StepRun],
    attempts_by_row: Mapping[UUID, Sequence[Attempt]],
    park_row: StepRun,
) -> CheckpointStory | None:
    """The done-checkpoint row's own Story frame, read the same way `skip_story` and the
    Stories strip already do (`rows_in_frame`/`story_frame`) — nothing here is specific to
    a checkpoint beyond which frame it is asked about. `build_alert` only calls this with a
    real `park_row` (it is the caller's own `park_row is not None` guard), so the one thing
    left to answer `None` for is a checkpoint row outside any Story frame at all."""
    frame = story_frame(park_row.path)
    if frame is None:
        return None
    frame_rows = rows_in_frame(rows, frame)
    build_row = next((row for row in frame_rows if row.kind == AGENT_KIND), None)
    commit_row = next((row for row in frame_rows if row.kind == COMMIT_KIND), None)
    verify_row = next((row for row in frame_rows if row.kind == SHELL_KIND), None)
    attempts = len(attempts_by_row.get(build_row.id, ())) if build_row is not None else 0
    cost = Decimal("0")
    for frame_row in frame_rows:
        for one in attempts_by_row.get(frame_row.id, ()):
            cost += one.cost_usd or Decimal("0")
    return CheckpointStory(
        story_id=park_row.story_id or "",
        title=_title(commit_row),
        attempts=attempts,
        cost_usd=cost,
        verify=verify_row.status if verify_row is not None else "",
    )


def _title(commit_row: StepRun | None) -> str:
    if commit_row is None:
        return ""
    message = str(commit_row.with_resolved.get(COMMIT_MESSAGE_KEY, ""))
    match = _TITLE_IN_MESSAGE.match(message)
    return match["title"] if match else ""
