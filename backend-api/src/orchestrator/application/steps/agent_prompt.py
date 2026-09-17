"""Pure prompt builder for the `agent` kind (AD-9, FR-14).

All constants and `compose_prompt` live here so `agent.py` stays within the 400-line cap.
No I/O imports — the caller reads any `prompt_file` and passes the content in.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from orchestrator.application.steps import agent_answer
from orchestrator.application.steps.agent_answer import (
    ANSWER_EVENT,
    ANSWER_KEY,
    CONDITION_KEY,
)
from orchestrator.application.steps.context import resolved_text
from orchestrator.application.templates.agent_row import (
    PROMPT_EXTRA_KEY,
    SPEC_FOLDER_KEY,
    STORY_ID_KEY,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord

#: The prompt, in the pieces FR-14 pins. Asserted verbatim by the prompt tests.
DISPATCH = (
    "Run the skill {skill} in folder+id dispatch mode: "
    "spec folder {spec_folder}, story id {story_id}."
)
HALT = " Halt after planning."
ANSWER = ' Answer from the operator to the blocking condition "{condition}": {answer}'
#: How a retry prompt reaches a *new* session: in front of the dispatch sentence the session
#: has not been told yet. A resumed one is sent the retry prompt alone.
RETRY_PROMPT = "{retry} {dispatch}"

#: The `with` key that carries a literal prompt string.
PROMPT_KEY = "prompt"
#: The `with` key that names a file whose content is used as the prompt base.
PROMPT_FILE_KEY = "prompt_file"

#: The `with` key for the skill dispatch form (kept here alongside its siblings).
SKILL_KEY = "skill"


def compose_prompt(
    with_resolved: Mapping[str, Any],
    resume_signal: GateRecord | None,
    previous_attempt: Attempt | None,
    *,
    prompt_file_content: str | None = None,
) -> str:
    """What the harness is asked, from the row the planner resolved (FR-14, AD-7).

    Base selection (exactly one of these fires):
    - `prompt` key present → use its value directly.
    - `prompt_file_content` provided → use the pre-read file content.
    - neither → the DISPATCH sentence (skill/folder/id form).

    `prompt_extra`, HALT, and ANSWER clauses are appended the same way for all three forms.
    `agent_answer.halts_after_planning` is the one place that decides the halt.
    """
    if PROMPT_KEY in with_resolved:
        base = str(with_resolved[PROMPT_KEY])
    elif prompt_file_content is not None:
        base = prompt_file_content
    else:
        base = DISPATCH.format(
            skill=resolved_text(with_resolved, SKILL_KEY),
            spec_folder=resolved_text(with_resolved, SPEC_FOLDER_KEY),
            story_id=resolved_text(with_resolved, STORY_ID_KEY),
        )
    parts = [base]
    payload = resume_signal.payload if resume_signal is not None else {}
    extra = resolved_text(with_resolved, PROMPT_EXTRA_KEY)
    if extra:
        parts.append(f" {extra}")
    if resume_signal is not None and resume_signal.event == ANSWER_EVENT:
        condition, answer = payload.get(CONDITION_KEY, ""), payload.get(ANSWER_KEY, "")
        parts.append(ANSWER.format(condition=condition, answer=answer))
    if agent_answer.halts_after_planning(with_resolved, resume_signal):
        parts.append(HALT)
    return "".join(parts)
