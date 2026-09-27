"""Pure prompt builder for the `agent` kind (AD-9, FR-14).

**Every sentence comes from the Template** (Operator decision, 2026-09-27): the row's
`prompts` clauses — `dispatch`, `rendered`, `answer`, `halt` — are the Template's own
prose, `{{ }}`-resolved by the planner, and this module only selects the clauses the
dispatch owes, fills their runtime placeholders, and joins the present parts with single
spaces. It writes no words of its own: a template that declares no clause sends none, and
an undeclared `answer` clause degrades to the Operator's raw answer text — their words,
not this module's. A separator is not prose: the one thing composed in code is the `" "`
between parts (and the retry join in `steps/agent.py::_planned`), which carries no words.

**Two substitution passes, by design.** `{{ }}` is the planner's (AD-7) and is gone before
a row ever reaches here. The single-brace tokens below are runtime facts the planner cannot
know — the rendered snapshot path, the Operator's answer, the `workdir`-absolutised spec
folder `agent_workdir.prompt_scope` rewrites — and they are filled in one `re.sub` pass
whose replacement values are inserted literally and never re-scanned, so braces inside
operator-authored intent or answer text are inert. A token the table below does not name
(`{storyid}`) stays literal prose.

No I/O imports — the caller reads any `prompt_file` and passes the content in.
"""

from __future__ import annotations

import re
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
    PROMPTS_KEY,
    SPEC_FOLDER_KEY,
    STORY_ID_KEY,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord

#: The `with` key that carries a literal prompt string.
PROMPT_KEY = "prompt"
#: The `with` key that names a file whose content is used as the prompt base.
PROMPT_FILE_KEY = "prompt_file"
#: The `with` key that carries a pasted intent — filled into the dispatch clause's
#: `{intent}` token (task@1's form).
INTENT_KEY = "intent"
#: The `with` key for the skill dispatch form (kept here alongside its siblings).
SKILL_KEY = "skill"

#: The clause names, as `templates/table.py::PROMPTS_KEYS` spells them.
DISPATCH_CLAUSE = "dispatch"
RENDERED_CLAUSE = "rendered"
ANSWER_CLAUSE = "answer"
HALT_CLAUSE = "halt"

#: Every runtime token a clause may name. One pattern rather than one per clause: which
#: tokens actually fill is decided by the values each call passes, and an unfilled one
#: stays literal — never an error inside a durable step.
PLACEHOLDER = re.compile(r"\{(skill|spec_folder|story_id|intent|path|condition|answer)\}")


def compose_prompt(
    with_resolved: Mapping[str, Any],
    resume_signal: GateRecord | None,
    previous_attempt: Attempt | None,
    *,
    prompt_file_content: str | None = None,
    workflow_path: str | None = None,
) -> str:
    """What the harness is asked: the row's own clauses, filled and joined (FR-14, AD-7).

    Base selection (exactly one of these fires):
    - `prompt` key present → its value, verbatim — the Template's own instructions.
    - `prompt_file_content` provided → the pre-read file content, verbatim.
    - otherwise → the row's `dispatch` clause, with `{skill}`, `{spec_folder}`,
      `{story_id}` and `{intent}` filled from the row.

    `workflow_path` is the snapshot `agent_render` rendered for this row, when it rendered
    one; it fills the `rendered` clause, which prefixes the dispatch form and only that —
    `prompt` and `prompt_file` carry their own instructions and never render. The
    `prompt_extra`, `answer` and `halt` parts are appended the same way for all forms;
    `agent_answer.halts_after_planning` is the one place that decides the halt.

    Total over any row: a stored version with no clauses composes from empty parts rather
    than raising — validation is the guard, not this function.

    `previous_attempt` stays in the signature deliberately: it is the seam FR-14 reserves
    for a dispatch that must read the attempt before it, and every caller already holds it.
    """
    del previous_attempt  # reserved by FR-14's signature; nothing composed from it today
    clauses = _clauses(with_resolved)
    skill = resolved_text(with_resolved, SKILL_KEY)
    own_text = PROMPT_KEY in with_resolved or prompt_file_content is not None
    parts: list[str] = []
    if workflow_path is not None and not own_text:
        rendered = str(clauses.get(RENDERED_CLAUSE, ""))
        parts.append(_fill(rendered, {"skill": skill, "path": workflow_path}))
    parts.append(_base(with_resolved, clauses, skill, prompt_file_content))
    parts.append(resolved_text(with_resolved, PROMPT_EXTRA_KEY))
    if resume_signal is not None and resume_signal.event == ANSWER_EVENT:
        parts.append(_answer(clauses, resume_signal))
    if agent_answer.halts_after_planning(with_resolved, resume_signal):
        parts.append(str(clauses.get(HALT_CLAUSE, "")))
    return " ".join(part for part in parts if part)


def answer_clause(with_resolved: Mapping[str, Any], resume_signal: GateRecord) -> str:
    """The Answer part alone — what a resumed session is sent as its next turn.

    The same clause `compose_prompt` appends, so session mode (AD-13) and a fresh dispatch
    quote one sentence; a row that declares no `answer` clause sends the Operator's own
    words and nothing else.
    """
    return _answer(_clauses(with_resolved), resume_signal)


def _clauses(with_resolved: Mapping[str, Any]) -> Mapping[str, Any]:
    declared = with_resolved.get(PROMPTS_KEY)
    return declared if isinstance(declared, Mapping) else {}


def _base(
    with_resolved: Mapping[str, Any],
    clauses: Mapping[str, Any],
    skill: str,
    prompt_file_content: str | None,
) -> str:
    if PROMPT_KEY in with_resolved:
        return str(with_resolved[PROMPT_KEY])
    if prompt_file_content is not None:
        return prompt_file_content
    return _fill(
        str(clauses.get(DISPATCH_CLAUSE, "")),
        {
            "skill": skill,
            "spec_folder": resolved_text(with_resolved, SPEC_FOLDER_KEY),
            "story_id": resolved_text(with_resolved, STORY_ID_KEY),
            "intent": resolved_text(with_resolved, INTENT_KEY),
        },
    )


def _answer(clauses: Mapping[str, Any], resume_signal: GateRecord) -> str:
    payload = resume_signal.payload
    answer = str(payload.get(ANSWER_KEY, ""))
    declared = clauses.get(ANSWER_CLAUSE)
    if declared is None:
        return answer
    condition = str(payload.get(CONDITION_KEY, ""))
    return _fill(str(declared), {"condition": condition, "answer": answer})


def _fill(clause: str, values: Mapping[str, str]) -> str:
    """One literal-insertion pass: a value is never re-scanned for tokens of its own."""
    return PLACEHOLDER.sub(lambda match: values.get(match.group(1), match.group(0)), clause)
