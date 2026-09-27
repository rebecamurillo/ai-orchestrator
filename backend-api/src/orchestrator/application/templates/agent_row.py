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

**`prompt_extra` prefers what the Template bound.** `story@1` binds
`{{story.invoke_dev_with}}` itself, so the two agree; a Template that binds something else
means it, and one that binds nothing still gets the entry's own `invoke_dev_with`, because
that is the field the method uses to tell a dispatch what to read first (FR-14).

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

#: The list-file field an entry tells a dispatch what to read first in.
INVOKE_DEV_WITH = "invoke_dev_with"


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
    if agent.expect_files or agent.expect_status_in:
        return True
    return bool(frame.story_id) and bool(frame.scope.get(SPEC_FOLDER_KEY))


def prompt_extra(resolved: Mapping[str, Any], frame: Frame) -> str:
    """What the Template bound, or the entry's own `invoke_dev_with`, or nothing at all."""
    return str(resolved.get(PROMPT_EXTRA_KEY) or field(frame, INVOKE_DEV_WITH) or "")


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


def field(frame: Frame, name: str) -> Any:
    """One field of the bound entry, or `None` when there is no entry to read it off."""
    entry = item(frame)
    return None if entry is None else entry.get(name)
