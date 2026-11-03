"""What a stop's post is made of (story 3-3). Read inside the post's claim, under the Run
lock, so the facts are the stop's as it was claimed.

**The question and the senior's view.** A consult entry owns the stop when it sits on the
park row, or on the row whose entry's `park_path` is the Run's (a `verify_failed` consult
sits on its redispatch target), under `consults[park_kind]`, escalated or failed. Its park
reason is then `{question} · {view}` (`steps/agent_consult.py`'s `ESCALATED` and `FAILED`),
so the question is the entry's and the view is the rest. Otherwise the reason is the question.

**Earlier answers** are the `answer` and `senior_answer` records inside the stop's Story
frame, oldest first, the last `ANSWERS_SHOWN` of them. A `chat` answer is shown as
`{author} via {platform}`, from its payload (4-1).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from orchestrator.application.jobs.chat_ports import ChatPorts
from orchestrator.application.rules.chat_message import Answer, StopFacts, chat_author
from orchestrator.application.rules.consult import PARK_PATH_KEY, QUESTION_KEY, STATE_KEY
from orchestrator.application.rules.frames import epic_frame, in_frame, story_frame
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun

ANSWERS_SHOWN: Final = 3
#: The consult states whose stop the senior handed back to a person.
HANDED_BACK: Final = frozenset({"escalate", "failed"})
ANSWER_EVENT: Final = "answer"
ANSWER_EVENTS: Final = frozenset({ANSWER_EVENT, "senior_answer"})
#: Who an answer is shown as, by its record's actor.
WHO: Final = {"operator": "Operator", "terminal": "Operator", "senior": "Senior"}
#: A thread reply's answer, shown by its author and platform instead (4-1).
CHAT_ACTOR: Final = "chat"
REASON_SEPARATOR: Final = " · "


def stop_facts(chat: ChatPorts, run: Run, run_url: str | None) -> StopFacts:
    """The facts of the Run's current stop."""
    project = chat.projects.get(run.project_id)
    repository = chat.repositories.get(run.repository_id)
    rows = chat.writers.steps.list_for_run(run.id)
    park_row = next((row for row in rows if row.path == run.park_path), None)
    question, view = _question(run, rows)
    return StopFacts(
        project=project.name if project is not None else "",
        repository=repository.slug if repository is not None else "",
        park_kind=run.park_kind or "",
        park_seq=run.park_seq,
        folder=str(run.inputs.get("spec_folder") or run.inputs.get("initiative_folder") or ""),
        epic=_epic(run.park_path or ""),
        story_id=park_row.story_id if park_row is not None else None,
        row_label=park_row.label if park_row is not None else None,
        question=question,
        senior_view=view,
        answers=_answers(chat.writers.records.list_for_run(run.id), run.park_path or ""),
        run_url=run_url,
    )


def _question(run: Run, rows: Sequence[StepRun]) -> tuple[str | None, str | None]:
    reason = run.park_reason or ""
    asked = _asked(run, rows)
    prefix = f"{asked}{REASON_SEPARATOR}"
    if asked and reason.startswith(prefix):
        return asked, reason[len(prefix) :]
    return reason or None, None


def _asked(run: Run, rows: Sequence[StepRun]) -> str | None:
    """The question of the consult entry that owns this stop, if one does."""
    for row in rows:
        entry = row.consults.get(run.park_kind or "")
        if not isinstance(entry, dict) or entry.get(STATE_KEY) not in HANDED_BACK:
            continue
        if row.path == run.park_path or (
            run.park_path is not None and entry.get(PARK_PATH_KEY) == run.park_path
        ):
            return str(entry.get(QUESTION_KEY) or "")
    return None


def _epic(path: str) -> int | None:
    """The epic's position, 1-based, off the `epics[i]` frame of the park path."""
    frame = epic_frame(path)
    if frame is None:
        return None
    return int(frame[frame.rindex("[") + 1 : -1]) + 1


def _answers(records: Sequence[GateRecord], park_path: str) -> tuple[Answer, ...]:
    frame = story_frame(park_path)
    if frame is None:
        return ()
    picked = [
        Answer(_who(record), _text(record))
        for record in records
        if record.event in ANSWER_EVENTS
        and (record.actor in WHO or record.actor == CHAT_ACTOR)
        and record.path is not None
        and in_frame(record.path, frame)
    ]
    return tuple(picked[-ANSWERS_SHOWN:])


def _who(record: GateRecord) -> str:
    if record.actor == CHAT_ACTOR:
        payload = record.payload
        return chat_author(str(payload.get("author") or ""), str(payload.get("platform") or ""))
    return WHO[record.actor]


def _text(record: GateRecord) -> str:
    if record.event == ANSWER_EVENT:
        return str(record.payload.get("text") or "")
    return record.text
