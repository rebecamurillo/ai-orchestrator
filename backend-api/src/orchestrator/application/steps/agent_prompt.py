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
#: The `with` key that carries a pasted intent for the intent dispatch form (task@1).
INTENT_KEY = "intent"

#: The `with` key for the skill dispatch form (kept here alongside its siblings).
SKILL_KEY = "skill"
#: Prefix for intent dispatch. The `{skill}` placeholder is formatted (a validated slug);
#: the intent text is then concatenated raw, bypassing `.format()` to avoid treating
#: `{...}` patterns in the operator's intent as format specifiers.
DISPATCH_INTENT = "Run the skill {skill} with the following intent:\n\n"

#: What a row whose workflow this process already rendered says first (Operator finding,
#: 2026-09-21). It replaces the one instruction a small model could not carry out — resolve
#: two placeholders, run the renderer, follow what it prints — with the answer, and forbids
#: the renderer explicitly, because a model that runs it again with invented arguments gets
#: an argparse error and improvises from there. `agent_render.prerendered_workflow` is what
#: produces the path; a row that rendered nothing never sees this sentence.
PRERENDERED = (
    "The workflow for skill {skill} is already rendered at {path}. "
    "Read that file fully and follow it; every step, status and halt this dispatch owes "
    "is defined there. Do not run render_skill.py yourself. "
)


def compose_prompt(
    with_resolved: Mapping[str, Any],
    resume_signal: GateRecord | None,
    previous_attempt: Attempt | None,
    *,
    prompt_file_content: str | None = None,
    workflow_path: str | None = None,
) -> str:
    """What the harness is asked, from the row the planner resolved (FR-14, AD-7).

    Base selection (exactly one of these fires):
    - `prompt` key present → use its value directly.
    - `prompt_file_content` provided → use the pre-read file content.
    - `intent` key present → DISPATCH_INTENT prefix + intent text (concatenated raw to
      avoid `.format()` treating `{...}` patterns in the intent as placeholders).
    - none of the above → the folder+id DISPATCH sentence (skill/folder/id form).

    `workflow_path` is the snapshot `agent_render` rendered for this row, when it rendered
    one. It prefixes the two skill forms and only those: `prompt` and `prompt_file` carry
    their own instructions verbatim and name no skill, so there is nothing to point them at
    — and the dispatch sentence still follows the prefix, because the workflow's own first
    step reads the spec folder and story id out of it.

    `prompt_extra`, HALT, and ANSWER clauses are appended the same way for all forms.
    `agent_answer.halts_after_planning` is the one place that decides the halt.
    """
    prefix = ""
    if PROMPT_KEY in with_resolved:
        base = str(with_resolved[PROMPT_KEY])
    elif prompt_file_content is not None:
        base = prompt_file_content
    elif INTENT_KEY in with_resolved:
        prefix = _prerendered(with_resolved, workflow_path)
        base = DISPATCH_INTENT.format(skill=resolved_text(with_resolved, SKILL_KEY)) + str(
            with_resolved[INTENT_KEY]
        )
    else:
        prefix = _prerendered(with_resolved, workflow_path)
        base = DISPATCH.format(
            skill=resolved_text(with_resolved, SKILL_KEY),
            spec_folder=resolved_text(with_resolved, SPEC_FOLDER_KEY),
            story_id=resolved_text(with_resolved, STORY_ID_KEY),
        )
    parts = [prefix, base]
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


def _prerendered(with_resolved: Mapping[str, Any], workflow_path: str | None) -> str:
    """The PRERENDERED sentence for a row whose workflow was rendered, else nothing."""
    if workflow_path is None:
        return ""
    return PRERENDERED.format(skill=resolved_text(with_resolved, SKILL_KEY), path=workflow_path)
