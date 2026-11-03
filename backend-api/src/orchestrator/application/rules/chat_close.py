"""When a stop's thread closes, and what it says then (story 4-2, CAP-12, AD-24, AD-25).
Pure: no port, no I/O.

**A stop has ended** when its Run is no longer `needs_you` at the thread's `park_seq`. A lock
flag or a `park_kind` rewrite at the same `park_seq` does not end it.

**The record that ended it.** `gate_record` carries no `park_seq`, so the stop's park record
is counted back from the end: the `(run.park_seq - thread.park_seq + 1)`-th record whose event
is a park kind. That holds because every `park_seq` increment writes exactly one park-kind
record (`test_park_record_invariant.py` pins it). In the window after it and before the next
park record, the first ending signal or the expiry wins, then the first `budget_raise`, then
the first lifecycle end, then a `paused` next park. A resuming `budget_raise` followed by a
`cancel` while the Run runs reads `Run cancelled`: a known limitation.

**The words** never carry answer text, a question, a reason or a mention, so they are the same
under `metadata_only`. The Run link is the post's trusted suffix, as in `chat_message.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from orchestrator.application.rules.chat_message import (
    MAX_POST_CHARS,
    ChatPost,
    Measure,
    neutralise,
    plain_length,
)
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.statuses import PARK_KINDS, RUN_EXPIRED

WATCH_HOURS: Final = 24
WATCH_READS_PER_FIRE: Final = 5
AUTHOR_CAP: Final = 200

#: Each signal that ends a stop, and the verb it reads as.
VERBS: Final[Mapping[str, str]] = {
    "answer": "answered",
    "continue": "continued",
    "retry": "retried",
    "skip_step": "step skipped",
    "skip_story": "story skipped",
    "skip_epic": "epic skipped",
    "terminal_resume": "resumed",
    "cancel": "Run cancelled",
}
BUDGET_RAISE: Final = "budget_raise"
RAISED: Final = "budget raised"
REJECTED: Final = "rejected"
LIFECYCLE_ENDS: Final[Mapping[str, str]] = {
    "done": "the Run finished",
    "failed": "the Run failed",
    "cancelled": "the Run was cancelled",
}
BY: Final[Mapping[str, str]] = {
    "operator": "by the Operator (Run page or API)",
    "terminal": "from a terminal session",
    "senior": "by the senior",
    "machine": "by the orchestrator",
}
EXPIRED: Final = "Run expired"
PAUSED: Final = "the Run was paused"
STOP_ENDED: Final = "the stop ended"
AFTER_SESSION: Final = " after a senior session"
NO_LONGER_READ: Final = "Replies in this thread are no longer read."
CLOSED_THREAD: Final = "This thread is closed. Act on the Run page"

_PARKS: Final = frozenset[str](PARK_KINDS)

type _Wanted = Callable[[GateRecord], bool]


@dataclass(frozen=True)
class Ending:
    """The stop's park record, the record that ended it, and whether a senior session ended
    between them. Either record is `None` when it could not be found."""

    park: GateRecord | None
    record: GateRecord | None
    session: bool = False


def stop_ended(run: Run, thread: ChatThread) -> bool:
    return not (run.status == "needs_you" and run.park_seq == thread.park_seq)


def ending_record(records: Sequence[GateRecord], run_park_seq: int, thread_park_seq: int) -> Ending:
    """Which of the Run's `records`, oldest first, ended the thread's stop."""
    parks = [index for index, record in enumerate(records) if record.event in _PARKS]
    back = run_park_seq - thread_park_seq + 1
    if back < 1 or back > len(parks):
        return Ending(park=None, record=None)
    start = parks[-back]
    end = parks[-back + 1] if back > 1 else len(records)
    window = list(enumerate(records[start + 1 : end], start + 1))
    chosen = (
        _first(window, lambda record: record.event in VERBS or _expiry(record))
        or _first(window, lambda record: record.event == BUDGET_RAISE)
        or _first(window, lambda record: record.event in LIFECYCLE_ENDS)
    )
    if chosen is None and end < len(records) and records[end].event == "paused":
        chosen = (end, records[end])
    if chosen is None:
        return Ending(park=records[start], record=None)
    index, record = chosen
    session = any(between.event == "session_end" for between in records[start + 1 : index])
    return Ending(park=records[start], record=record, session=session)


def how(ending: Ending) -> str:
    """How the stop ended, in the closing notice's words."""
    record = ending.record
    if record is None:
        return STOP_ENDED
    if record.event in _PARKS:
        return PAUSED
    if _expiry(record):
        return EXPIRED
    if record.event in LIFECYCLE_ENDS:
        return LIFECYCLE_ENDS[record.event]
    verb = RAISED if record.event == BUDGET_RAISE else VERBS[record.event]
    if record.event == "answer" and ending.park is not None and ending.park.event == "checkpoint":
        verb = REJECTED
    words = f"{verb} {_by(record)}"
    return words + AFTER_SESSION if ending.session else words


def close_line(
    ending: Ending, park_seq: int, run_url: str | None, measure: Measure = plain_length
) -> ChatPost:
    """The closing notice of stop `park_seq`, within the limit, its link kept."""
    text = f"Closed · stop {park_seq} · {how(ending)}\n{NO_LONGER_READ}"
    return _fitted(ChatPost(text, f"\nRun: {run_url}" if run_url else ""), measure)


def closed_mention_line(run_url: str | None, measure: Measure = plain_length) -> ChatPost:
    """The one notice a closed thread gets for a later mention."""
    if run_url is None:
        return _fitted(ChatPost(f"{CLOSED_THREAD}."), measure)
    return _fitted(ChatPost(f"{CLOSED_THREAD}:", f" {run_url}"), measure)


def _by(record: GateRecord) -> str:
    if record.actor != "chat":
        return BY[record.actor]
    platform = _one_line(str(record.payload.get("platform") or ""))
    author = record.payload.get("author")
    if not isinstance(author, str) or not author:
        return f"by a chat reply via {platform}"
    return f"by {_one_line(author)} via {platform}"


def _one_line(text: str) -> str:
    return neutralise(text).replace("\n", " ")[:AUTHOR_CAP]


def _expiry(record: GateRecord) -> bool:
    return record.event == "failed" and record.actor == "machine" and record.text == RUN_EXPIRED


def _first(window: list[tuple[int, GateRecord]], wanted: _Wanted) -> tuple[int, GateRecord] | None:
    return next(((index, record) for index, record in window if wanted(record)), None)


def _fitted(post: ChatPost, measure: Measure) -> ChatPost:
    """`post` with its text cut from the end until it fits; the suffix always stays."""
    text = post.text
    overflow = measure(post) - MAX_POST_CHARS
    while overflow > 0 and text:
        text = text[: max(len(text) - overflow, 0)]
        overflow = measure(ChatPost(text, post.suffix)) - MAX_POST_CHARS
    return ChatPost(text, post.suffix)
