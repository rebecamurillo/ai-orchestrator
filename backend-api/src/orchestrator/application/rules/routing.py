"""FR-16, as one pure function: what the Story file the agent wrote says happens next.

The whole point of the rule is that a harness's exit code, its output, or its mood never
counts as done — the file does. So this module takes no port, no clock and no repository: the
glob has already been asked, the file has already been parsed, and what is left is a table.
`application/steps/agent_tail.py` is the only caller; it does the reading and adds the log
path to whatever comes back.

**The order is liveness, then status.** Zero or several matches, or one that would not parse,
is a `misconfigured` stop whatever any file happened to say — a Run that acted on one of two
Story files would be acting on a guess. Only then does the status decide, and only then can
a non-zero exit code mean anything: FR-16 lets the code overrule a `done` file and nothing
else, because a `blocked` file is the agent reporting deliberately and the code it exited
with says nothing the file has not already said.

The one thing the exit code does *before* that is name a failure the rule has already
reached: an empty glob reads `harness exit {code}` rather than `no story file` when the
process itself died, because the two send an Operator somewhere different. `_liveness` has
the argument and the reasoning.

**`expect.status_in` is not consulted here.** The Template's list is what the *planner*
validates a Template against; the routing tokens are FR-16's, fixed, and they differ on
purpose: the shipped `story@1` lists `ready-for-dev` as expected, yet `ready-for-dev` without
a declared spec checkpoint is a Story that stopped early and takes the retry path.

**Nothing here is ever retried automatically except the retry path itself** (AD-9). `blocked`
is a question for the Operator; every liveness failure and every configuration condition is
`misconfigured`, and a `misconfigured` Run waits for a person. The retry path is bounded by
the row's own counter against the contract's `max`, and when it is used up the same sentence
becomes the park reason — so the Operator reads the same words the gate record counted.
"""

from __future__ import annotations

from collections.abc import Sequence

from orchestrator.application.story_file import StoryFile
from orchestrator.domain.statuses import Gate
from orchestrator.domain.values import Park, Retry, StepResult

#: The three statuses FR-16 routes forward, by name.
DONE = "done"
BLOCKED = "blocked"
READY_FOR_DEV = "ready-for-dev"

#: The `Blocking condition:` texts that are a broken installation rather than a question.
#: A stop on one of these offers no Answer box — the Run detail reads `park_kind`, and this
#: park is `misconfigured`, not `blocked` (PRD §4.6, FR-16).
CONFIGURATION_CONDITIONS: tuple[str, ...] = (
    "no subagents",
    "no stories.yaml found",
    "story id not found in stories.yaml",
    "version-control metadata not writable",
    "no epic spec found",
    "unrecognized status in existing story file",
    "ambiguous story file match",
)

#: Every reason this rule can leave, verbatim as PRD §4.6 prints them.
NO_STORY_FILE = "no story file"
AMBIGUOUS_STORY_FILE = "ambiguous story file: {names}"
UNREADABLE_FRONTMATTER = "no story file: frontmatter unreadable in {name}"
MISCONFIGURED_HARNESS = "harness misconfigured: {condition}"
UNEXPECTED_STATUS = "unexpected status: {status}"
HARNESS_EXIT = "harness exit {code}"
SPEC_CHECKPOINT = "spec checkpoint"

#: How the names of several matches are joined into one sentence.
NAME_SEPARATOR = ", "


def route(  # noqa: PLR0913, PLR0917 — the FR-16 table's own columns, in its own order
    story_file: StoryFile | None,
    files: Sequence[str],
    exit_code: int | None,
    spec_checkpoint: bool,
    retry_count: int,
    retry: Retry | None,
    *,
    gate: Gate,
    path: str,
) -> StepResult:
    """What the dispatch reached, by FR-16's table alone.

    `gate` and `path` are keyword-only because they are facts of the *row* rather than of the
    contract: the gate the planner recorded (AD-7) travels back out unchanged on every
    result, and `Park.path` names the row that stopped the Run. Everything else is what the
    dispatch left behind.
    """
    live = _liveness(story_file, files, exit_code)
    if live is not None:
        return _parked(live, gate=gate, path=path)
    assert story_file is not None  # `_liveness` answers for every other shape
    if story_file.status == BLOCKED:
        return _blocked(story_file, gate=gate, path=path)
    if story_file.status == READY_FOR_DEV and spec_checkpoint:
        return StepResult(
            status="checkpoint",
            gate=gate,
            reason=SPEC_CHECKPOINT,
            park=Park(kind="checkpoint", reason=SPEC_CHECKPOINT, path=path),
        )
    if story_file.status != DONE:
        reason = UNEXPECTED_STATUS.format(status=story_file.status)
        return _retry(reason, retry, retry_count, gate=gate, path=path)
    if exit_code:
        # `None` and `0` are both "the harness reported no failure": only a timeout produces
        # `None`, and the executor parked that before this rule was ever reached.
        return _retry(HARNESS_EXIT.format(code=exit_code), retry, retry_count, gate=gate, path=path)
    return StepResult(status="done", gate=gate)


def _liveness(
    story_file: StoryFile | None, files: Sequence[str], exit_code: int | None
) -> str | None:
    """The reason the glob's answer is not one readable file, or `None` when it is.

    **Why the exit code is read for the no-file case, and only there** (Operator decision,
    2026-09-20). "No file" has two causes that look identical from here: an agent that ran and
    chose to write nothing, and a CLI that died before it read the prompt. Both stop the Run
    the same way — a `misconfigured` park, never auto-retried — but they send the Operator to
    two different places, and `no story file` sent them to the wrong one for every OpenCode
    dispatch on a gateway-enabled install, because an unparseable config killed the CLI in a
    second and the Run reported a missing document.

    This does not soften the module's claim that the file decides `done`: a non-zero exit is
    still never an outcome here, only the sentence attached to a failure the rule had already
    reached. The `exit_code` overrule below — a `done` file contradicted by a failed process —
    is untouched, and a zero-exit empty glob still reads `no story file`.
    """
    if not files:
        return HARNESS_EXIT.format(code=exit_code) if exit_code else NO_STORY_FILE
    if len(files) > 1:
        return AMBIGUOUS_STORY_FILE.format(names=NAME_SEPARATOR.join(sorted(files)))
    if story_file is None:
        return UNREADABLE_FRONTMATTER.format(name=files[0])
    return None


def _blocked(story_file: StoryFile, *, gate: Gate, path: str) -> StepResult:
    """A `blocked` file: the Operator's question, unless the condition says it is ours."""
    if story_file.blocking_condition in CONFIGURATION_CONDITIONS:
        reason = MISCONFIGURED_HARNESS.format(condition=story_file.blocking_condition)
        return _parked(reason, gate=gate, path=path)
    section = story_file.auto_run_result
    return StepResult(
        status="blocked",
        gate=gate,
        reason=section,
        park=Park(kind="blocked", reason=section, path=path),
    )


def _retry(reason: str, retry: Retry | None, count: int, *, gate: Gate, path: str) -> StepResult:
    """One more bounded attempt at this row, or the park its bound turns into (AD-9)."""
    if retry is not None and count < retry.max:
        return StepResult(status="error", gate=gate, reason=reason, retry=retry)
    return _parked(reason, gate=gate, path=path)


def _parked(reason: str, *, gate: Gate, path: str) -> StepResult:
    """The one stop kind every failure of this rule maps to; never retried (AD-9)."""
    return StepResult(
        status="error",
        gate=gate,
        reason=reason,
        park=Park(kind="misconfigured", reason=reason, path=path),
    )
