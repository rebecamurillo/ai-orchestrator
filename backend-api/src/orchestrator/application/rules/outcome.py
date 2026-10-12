"""O-6: the phrase a `protected_path` park appends for the outcome it is hiding."""

from __future__ import annotations

from orchestrator.domain.values import StepResult

STORY_DONE = "story done"
STORY_BLOCKED = "story blocked: {condition}"
STALLED = "stalled"
TIMED_OUT = "timed out"


def routed_outcome(routed: StepResult, blocking_condition: str | None) -> str:
    """What `routing.route` reached, in a few words; a stop's own reason when it has one."""
    if routed.park is None and routed.retry is None:
        return STORY_DONE
    if routed.park is not None and routed.park.kind == "blocked":
        return STORY_BLOCKED.format(condition=blocking_condition or routed.park.reason)
    return routed.reason or STORY_DONE
