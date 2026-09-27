"""What an `agent` row carries beyond its `with`, resolved once at plan time.

An `agent` step is the only kind whose row needs more than the Template wrote next to it:
the harness is dispatched into a Spec folder, on one entry of a list file, with the
entry's own instructions, and with the `expect` and `retry` contract the Template declared
as siblings of `with` rather than inside it. AD-7 says the plan decides all of that before
anything starts, so it is decided here and never at dispatch time — a `retry` prompt naming
`{{story.id}}` would otherwise be filled in from a branch that had moved on.

**The entry is never found by the name `story`.** Two shapes bind one: a `for_each` in the
same file binds it under the loop's `as` name, and a callee — which is how `epic@1` reaches
`story@1` — is handed it as the input it declared `item` (AD-15). Either way the Template
chose the name, so neither is guessed. A Template with no entry at all is not a broken row:
an `agent` step outside every loop is a dispatch with no Story behind it, and the three keys
that describe one read `None`.

**`prompt_extra` is what the Template bound, full stop** (Operator decision, 2026-09-27).
`story@1` binds `{{story.invoke_dev_with}}` itself; a Template that binds something else
means it, and one that binds nothing appends nothing — the old fallback to the entry's own
`invoke_dev_with` was method knowledge living in code rather than in the file.

`pause_when` is the one agent extra that is *not* a row: a stop declared on the step is how
the step behaves, not a stop before or after it, so it stays the flag 4.6 reads (AD-7).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from orchestrator.application.templates.expressions import ITEM_TYPE
from orchestrator.application.templates.model import AgentExtras
from orchestrator.application.templates.substitute import paused, resolve
from orchestrator.application.templates.table import WRITES_KEY

if TYPE_CHECKING:  # a frame is the walker's; naming it here would be a second one
    from orchestrator.application.templates.rows import Frame

#: The list entry this row works on, whole — what a harness reads `id` and `title` off.
STORY_KEY = "story"
#: The entry's id, beside `PlannedRow.story_id`, so a dispatch needs only the row's `with`.
STORY_ID_KEY = "story_id"
#: The folder holding `SPEC.md`, `stories.yaml` and `stories/` — where a dispatch happens.
SPEC_FOLDER_KEY = "spec_folder"
#: What is appended to the harness prompt (FR-14).
PROMPT_EXTRA_KEY = "prompt_extra"
#: The Template's own prose for the dispatch, one clause per moment (Operator decision,
#: 2026-09-27): `{{ }}` resolved here at plan time (AD-7), single-brace runtime tokens —
#: `{skill}`, `{path}`, `{condition}`, `{answer}` … — left for `compose_prompt` to fill.
PROMPTS_KEY = "prompts"
#: `pause_when`, resolved: whether this Story stops for a spec review after planning.
SPEC_CHECKPOINT_KEY = "spec_checkpoint"
#: The `expect` and `retry` contracts, flattened by the parser and re-nested for the row.
EXPECT_KEY = "expect"
RETRY_KEY = "retry"
#: `escalate_when`, carried verbatim. Its grammar is `output.status == <token>` — a question
#: about what the harness reported, not about anything a Run could substitute — so there is
#: nothing to resolve. No executor in this epic reads it; it is on the row because AD-7 says
#: the plan decides, and a Template that declared it must not have it dropped on the way.
ESCALATE_WHEN_KEY = "escalate_when"


def agent_extras(agent: AgentExtras, frame: Frame) -> dict[str, Any]:
    """Everything an `agent` row carries beside the `with` its Template wrote."""
    entry = item(frame)
    extras: dict[str, Any] = {
        STORY_KEY: entry,
        STORY_ID_KEY: frame.story_id,
        SPEC_FOLDER_KEY: frame.scope.get(SPEC_FOLDER_KEY),
        SPEC_CHECKPOINT_KEY: paused(agent.pause_when, frame.scope),
        ESCALATE_WHEN_KEY: agent.escalate_when,
        WRITES_KEY: [resolve(path, frame.scope) for path in agent.writes],
        EXPECT_KEY: {
            "files": [resolve(glob, frame.scope) for glob in agent.expect_files],
            "status_in": list(agent.expect_status_in),
            # The declared result contract (Operator decision, 2026-09-27) — literal
            # tokens, like `status_in`: a status a method writes is not an expression.
            "success": list(agent.expect_success),
            "blocked": list(agent.expect_blocked),
            "checkpoint": list(agent.expect_checkpoint),
            "misconfigured_when": list(agent.expect_misconfigured_when),
        },
        RETRY_KEY: {
            "max": agent.retry_max,
            "prompt": resolve(agent.retry_prompt, frame.scope),
            "resume_session": agent.retry_resume_session,
        },
    }
    if not _has_story_contract(agent, frame):
        del extras[EXPECT_KEY]
    clauses = _prompt_clauses(agent, frame)
    if clauses:
        extras[PROMPTS_KEY] = clauses
    return extras


def _prompt_clauses(agent: AgentExtras, frame: Frame) -> dict[str, str]:
    """Each declared clause, plan-time resolved; an undeclared one stays off the row."""
    declared = (
        ("dispatch", agent.prompt_dispatch),
        ("rendered", agent.prompt_rendered),
        ("answer", agent.prompt_answer),
        ("halt", agent.prompt_halt),
    )
    return {name: resolve(text, frame.scope) for name, text in declared if text is not None}


def _has_story_contract(agent: AgentExtras, frame: Frame) -> bool:
    declared = (
        agent.expect_files,
        agent.expect_status_in,
        agent.expect_success,
        agent.expect_blocked,
        agent.expect_checkpoint,
        agent.expect_misconfigured_when,
    )
    if any(declared):
        return True
    return bool(frame.story_id) and bool(frame.scope.get(SPEC_FOLDER_KEY))


def prompt_extra(resolved: Mapping[str, Any], frame: Frame) -> str:
    """Exactly what the Template bound, or nothing at all (Operator decision, 2026-09-27:
    the `invoke_dev_with` fallback was method knowledge in code — a Template that wants the
    entry's field binds `prompt_extra: "{{story.invoke_dev_with}}"`, as the shipped ones do).
    """
    del frame  # the entry no longer supplies anything the Template did not bind
    return str(resolved.get(PROMPT_EXTRA_KEY) or "")


def item(frame: Frame) -> Mapping[str, Any] | None:
    """The list entry this row works on, from whichever of the two shapes bound it.

    A `for_each` in the same file binds its entry under the loop's `as` name; a callee —
    which is how `epic@1` reaches `story@1` — sees only what the call passed it, and says
    which of its inputs is the entry by declaring that input `item` (AD-15).
    """
    bound = frame.scope.get(frame.item_name) if frame.item_name else _declared(frame)
    return bound if isinstance(bound, Mapping) else None


def _declared(frame: Frame) -> Any:
    """What this Template's `item` input holds, where it declared one."""
    names = [decl.name for decl in frame.template.inputs if decl.type == ITEM_TYPE]
    return frame.scope.get(names[0]) if names else None
