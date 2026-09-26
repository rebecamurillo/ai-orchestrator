"""FR-18's **Answer**: what the Operator's paragraph does to the worktree, and what it says
to the harness (AD-9, AD-13, SPEC CAP-1).

Split out of `steps/agent.py` for the reason `agent_tail.py` was: that module is at its
400-line cap, and this is one subject of its own — the archive, the block appended to it,
and the two facts the prompt's Answer clause is built from. The dependency runs one way:
`agent.py` imports this module and re-exports the three payload names below, so
`steps.agent.ANSWER_EVENT` stays reachable where it always was, and nothing here imports
`agent.py` back.

**The archive is the whole mechanism, and it is why the re-dispatch plans fresh.** A Story
file at `{spec_folder}/stories/{id}-*.md` is what `bmad-build-auto` resumes from; moving it
to `stories/.answers/{id}-attempt-{n}.md` leaves the glob empty, so the next dispatch is a
first dispatch and the agent plans again — this time with the Operator's answer in front of
it. `n` is the *previous* attempt's number, because the file being archived is the one that
attempt wrote. Both ends of the move are returned so `agent.py` stages them into the prepare
commit: an unstaged rename would still be in the tree at `start_sha`, and 5.6 would read it
as the agent's own edit (AD-17, FR-31).

**Exactly one match, or nothing.** The brief scopes the archive to a single
`stories/{id}-*.md`; none is logged and proceeds as a first dispatch, and *more* than one is
left alone on purpose — two files is the `ambiguous story file` misconfiguration the routing
already refuses to guess at (`agent_tail.archive_ambiguous` is the only thing allowed to
resolve it, and only after the Operator asked for a Retry). Moving one of two here would
make that choice silently, at the moment a person is least able to see it.

**The condition is read back out of the archived file, not out of the signal.** `signal_run`
stores the Operator's own words under `rules/signals.py::ANSWER_KEY` and stores nothing
about what was asked, because the question is already on disk: it is the
`Blocking condition:` line of the `## Auto Run Result` section the agent wrote. A spec
checkpoint has no such line — nothing failed, the plan was rejected — so the clause is built
from `spec rejected` instead, which is what the row's own `spec_checkpoint` flag selects.

`resolved_signal` is where those two facts meet `compose_prompt`. That function is pure over
the values the planner resolved and holds no `Workspace`, so it cannot read a file; it takes
its Answer clause from the resume record's payload under `CONDITION_KEY` and `ANSWER_KEY`.
This module resolves both into a copy of that record. The copy is local to the dispatch and
never stored — the gate record the Operator's signal wrote is append-only (AD-8).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import structlog

from orchestrator.application.rules import protected_paths
from orchestrator.application.steps import agent_tail
from orchestrator.application.steps.context import (
    StepContext,
    require_cwd,
    require_workspace,
    resolved_text,
)
from orchestrator.application.story_file import (
    AUTO_RUN_RESULT,
    appended,
    blocking_condition,
    section,
)
from orchestrator.application.templates.agent_row import (
    SPEC_CHECKPOINT_KEY,
    SPEC_FOLDER_KEY,
    STORY_ID_KEY,
)
from orchestrator.domain.entities.gate_record import GateRecord

log = structlog.get_logger(__name__)

#: The gate record event an Answer wrote, and the two keys `compose_prompt` reads its clause
#: from. They are this module's contract with that function, not the signal's own: the
#: Operator's payload carries `rules/signals.py::ANSWER_KEY` ("text") and no condition at all.
ANSWER_EVENT = "answer"
CONDITION_KEY = "condition"
ANSWER_KEY = "answer"

#: Where the Operator's answer arrives, as `signal_run` stored it. Named here rather than
#: imported from `rules/signals.py` for the same reason `story_file.py` matches the
#: frontmatter fence rather than importing it: one is the signal's storage contract and one
#: is this dispatch's read of it, and tying them together would make a rename of either a
#: change to both. The two are asserted equal by this module's own test.
TEXT_KEY = "text"

#: The archive, exactly as FR-18 names it, under `agent_tail.ANSWERS_DIRECTORY`.
ARCHIVED_NAME = "{story_id}-attempt-{n}.md"

#: What is appended to the archived file. `story_file.appended` supplies the blank line in
#: front and the newline at the end, so this is the block itself.
HUMAN_ANSWER = "## Human Answer\n\n{at} · operator\n\n{answer}"

#: What a resume with nothing to archive logs. A first dispatch is a valid outcome here —
#: an agent that blocked before writing its Story file leaves the glob empty — so this is an
#: `info` line naming the row, never a park.
NO_FILE_TO_ARCHIVE = "no file to archive"

#: The condition a spec checkpoint's Answer quotes back: the plan was read and refused, so
#: there is no `Blocking condition:` line anywhere to read (6.2 sends this as a Reject).
SPEC_REJECTED = "spec rejected"


def answering(ctx: StepContext) -> GateRecord | None:
    """The Answer that resumed this row, or `None` for every other way it was reached.

    Returns the record rather than a boolean so the two callers below never have to ask
    `ctx.resume_signal` a second question the type checker cannot see they already asked.
    """
    signal = ctx.resume_signal
    if signal is not None and signal.event == ANSWER_EVENT:
        return signal
    return None


def archive_with_answer(ctx: StepContext) -> tuple[str, ...]:
    """FR-18's move, with the Operator's words appended — both paths, or `()`.

    Returned as `(source, destination)` so the caller stages the rename whole; see the
    module docstring for why an unstaged one would be attributed to the agent.

    **An untracked source is the destination alone** (Operator decision, 2026-09-26). The
    reason to stage a rename's source is that the tree at `start_sha` still holds it; a file
    git never tracked is in no tree, so there is nothing there to attribute and nothing for
    `git add` to match once the move has happened — it exits 128 on the pathspec. The
    question is asked *before* the move, which is the only moment it can be answered.
    """
    signal = answering(ctx)
    if signal is None:
        return ()
    matches = agent_tail.story_files(ctx) or ()
    if len(matches) != 1:
        if not matches:
            log.info(NO_FILE_TO_ARCHIVE, path=ctx.row.path, story_id=_story_id(ctx))
        return ()
    source, destination = matches[0], archive_path(ctx)
    never_tracked = source in protected_paths.untracked(ctx.ports.git.status(require_cwd(ctx)))
    workspace = require_workspace(ctx, ctx.cwd)
    workspace.move(source, destination)
    block = HUMAN_ANSWER.format(at=_iso(ctx.ports.clock.now()), answer=answer_text(signal))
    workspace.write(destination, appended(workspace.read(destination) or "", block))
    return (destination,) if never_tracked else (source, destination)


def archive_path(ctx: StepContext) -> str:
    """`{spec_folder}/stories/.answers/{id}-attempt-{n}.md`, the one name FR-18 pins.

    Pure, and computed the same way twice on purpose: the prepare phase moves the file to
    it, and the dispatch that follows reads the condition back out of it, with nothing
    carried between them but the row itself.
    """
    answers = agent_tail.ANSWERS_DIRECTORY.format(spec_folder=_text(ctx, SPEC_FOLDER_KEY))
    return f"{answers}/{ARCHIVED_NAME.format(story_id=_story_id(ctx), n=previous_n(ctx))}"


def previous_n(ctx: StepContext) -> int:
    """The attempt that wrote the file being archived — the one before this dispatch.

    Read off `previous_attempt` where there is one, which is every resume: a row only
    reaches an Answer by having parked. The fallback keeps the name derivable for a context
    that recorded none rather than raising inside a durable step.
    """
    previous = ctx.previous_attempt
    return previous.n if previous is not None else max(ctx.attempt.n - 1, 1)


def halts_after_planning(
    with_resolved: Mapping[str, Any], resume_signal: GateRecord | None
) -> bool:
    """Whether `compose_prompt` appends `HALT` (story 6-2, FR-19): a first dispatch or a
    re-plan at a spec checkpoint (`resume_signal is None`), and once more on a Reject there
    — the same `answer` signal this module's archive already fires on, at a row whose
    `spec_checkpoint` is still true because the Operator sent the plan back rather than
    approving it. `continue` and every other resume must not halt twice, which is why this
    is not simply "any resume at a spec checkpoint": a Continue means the plan was approved,
    and halting again would park the Run on the stop it just left."""
    if not with_resolved.get(SPEC_CHECKPOINT_KEY):
        return False
    return resume_signal is None or resume_signal.event == ANSWER_EVENT


def resolved_signal(ctx: StepContext) -> GateRecord | None:
    """`ctx.resume_signal` with the Answer clause's two values resolved onto its payload.

    Every other resume is handed back unchanged, so this is safe to call for any dispatch.
    """
    signal = answering(ctx)
    if signal is None:
        return ctx.resume_signal
    payload = {
        **signal.payload,
        CONDITION_KEY: condition(ctx),
        ANSWER_KEY: answer_text(signal),
    }
    return signal.model_copy(update={"payload": payload})


def condition(ctx: StepContext) -> str:
    """What the agent is told it is answering: the archived file's blocking condition.

    `spec rejected` at a spec checkpoint, where nothing failed and no such line exists. A
    file that states no condition — or one that is not where it was archived to, which is
    the "nothing to archive" case — answers `""`, and the clause renders with empty quotes
    rather than failing a dispatch over a missing sentence.
    """
    if ctx.with_resolved.get(SPEC_CHECKPOINT_KEY):
        return SPEC_REJECTED
    text = require_workspace(ctx, ctx.cwd).read(archive_path(ctx)) or ""
    return blocking_condition(section(text, AUTO_RUN_RESULT)) or ""


def answer_text(signal: GateRecord) -> str:
    """What the Operator typed, as `signal_run` stored it — `""` for a payload without it."""
    return str(signal.payload.get(TEXT_KEY, ""))


def _iso(moment: datetime) -> str:
    """ISO 8601 UTC with `Z` — the one time format this system writes (root AGENTS.md)."""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _story_id(ctx: StepContext) -> str:
    return _text(ctx, STORY_ID_KEY)


def _text(ctx: StepContext, key: str) -> str:
    return resolved_text(ctx.with_resolved, key)
