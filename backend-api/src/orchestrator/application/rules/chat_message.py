"""The words `chat_poll` posts (story 3-3, AD-25): a stop's thread, its reminder, and the
one-line notice of a senior's test-edit acceptance. Pure: no port, no I/O.

No platform syntax lives here. Each adapter renders its own mentions and neutralises its own
markup; this module only writes plain lines and keeps untrusted text from starting one.

**Untrusted text** (a question, a senior's view, an answer, a notice's files and reason) can
hold anything an agent or a person wrote. Every `Cc` character but `\\n` and every bidi
control is dropped, then each continuation line is prefixed with `CONTINUATION`, so such
text never opens a line, a fence, a heading or a quote. The facts this system wrote itself
go through the same cleaning, since a label or a folder can echo a file an agent wrote.

**Length** is counted in code points. Each field has its cap; the whole text is then held
to `MAX_POST_CHARS` by cutting whole answer lines oldest first, then the senior's view from
its end, then the question from its end. Whatever was cut, `CUT_MARKER` stands once on its
own line before the action line, and the action line and the Run link always stay.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Final
from uuid import UUID

MAX_POST_CHARS: Final = 3000
#: The cap on a project, a repository, a folder, a story id and a row label.
FIELD_CAP: Final = 200
QUESTION_CAP: Final = 1500
SENIOR_VIEW_CAP: Final = 600
ANSWER_CAP: Final = 200
REASON_CAP: Final = 600
#: How many file names a senior-accept line lists before `and {n} more`.
FILES_SHOWN: Final = 10

#: Two spaces and U+203A, so a continuation line of untrusted text opens with no markup.
CONTINUATION: Final = "  \u203a "
CUT_MARKER: Final = "… (cut; the Run page has the rest)"
REPLY_ACTION: Final = (
    "Reply in this thread and mention the bot to answer. The first allowed reply resumes the agent."
)
PAGE_ACTION: Final = "Act on the Run page."
#: The only stop whose thread takes a reply (AD-25, 4-1 amendment).
REPLY_STOP: Final = "blocked"

_BIDI: Final = frozenset(chr(code) for code in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))


@dataclass(frozen=True)
class Answer:
    """One earlier answer in the stop's Story: who gave it, as a word, and what it said."""

    who: str
    text: str


@dataclass(frozen=True)
class StopFacts:
    """What a stop's post says. A `None` or empty fact leaves its line out."""

    project: str
    repository: str
    park_kind: str
    park_seq: int
    folder: str = ""
    epic: int | None = None
    story_id: str | None = None
    row_label: str | None = None
    question: str | None = None
    senior_view: str | None = None
    answers: tuple[Answer, ...] = ()
    run_url: str | None = None


@dataclass(frozen=True)
class AcceptFacts:
    """What a senior-accept notice says."""

    project: str
    repository: str
    story_id: str | None
    files: tuple[str, ...]
    reason: str
    run_url: str | None


@dataclass(frozen=True)
class _Body:
    """The parts of a stop's post the total cut may shorten, already cleaned and capped."""

    question: str
    view: str
    answers: tuple[Answer, ...]
    cut: bool
    head: tuple[str, ...]
    tail: tuple[str, ...]


def run_link(base_url: str, run_id: UUID) -> str | None:
    """The Run's page, `notify/format.py::run_url`'s path, or `None` with no base URL."""
    base = base_url.strip().rstrip("/")
    return f"{base}/workflows/{run_id}" if base else None


def action_line(park_kind: str) -> str:
    return REPLY_ACTION if park_kind == REPLY_STOP else PAGE_ACTION


def neutralise(text: str) -> str:
    """`text` with its controls dropped and every continuation line prefixed."""
    return _continued(_clean(text))


def compose_stop(facts: StopFacts, metadata_only: bool) -> str:
    """A stop's thread root: one fact per line, in the pinned order, within the limit."""
    head = [_capped(value, FIELD_CAP) for value in _head_values(facts)]
    question, view, answers = ("", ""), ("", ""), []
    if not metadata_only:
        question = _capped(facts.question or "", QUESTION_CAP)
        view = _capped(facts.senior_view or "", SENIOR_VIEW_CAP)
        answers = [(answer.who, _capped(answer.text, ANSWER_CAP)) for answer in facts.answers]
    texts = [*head, question, view, *(text for _, text in answers)]
    body = _Body(
        question=question[1],
        view=view[1],
        answers=tuple(Answer(who, text[1]) for who, text in answers),
        cut=any(cleaned != capped for cleaned, capped in texts),
        head=_head_lines(facts, [capped for _, capped in head]),
        tail=(action_line(facts.park_kind), *_link_line(facts.run_url)),
    )
    return _render(_fit(body))


def reminder_text(park_kind: str, park_seq: int, hours: int, run_url: str | None) -> str:
    """A reminder in the stop's thread; `park_kind` is the thread's, as it was at posting."""
    lines = [
        f"Still waiting · {park_kind} · stop {park_seq} · parked {hours} h",
        action_line(park_kind),
        *_link_line(run_url),
    ]
    return "\n".join(lines)


def accept_line(facts: AcceptFacts, metadata_only: bool) -> str:
    """The one channel line for a `senior_accept`, within the limit, its link kept."""
    head = f"{_field(facts.project)} / {_field(facts.repository)}"
    if facts.story_id:
        head += f" · story {_field(facts.story_id)}"
    link = f" · {facts.run_url}" if facts.run_url else ""
    if metadata_only:
        return f"{head} · the senior accepted test edits to {len(facts.files)} files{link}"
    body = f"the senior accepted test edits: {_files(facts.files)}"
    reason = _clean(facts.reason)[:REASON_CAP]
    if reason:
        body += f" · {_continued(reason)}"
    room = MAX_POST_CHARS - len(head) - len(" · ") - len(link)
    return f"{head} · {body[:room]}{link}"


def _clean(text: str) -> str:
    return "".join(
        character
        for character in text
        if character == "\n" or not (unicodedata.category(character) == "Cc" or character in _BIDI)
    )


def _continued(text: str) -> str:
    return text.replace("\n", f"\n{CONTINUATION}")


def _capped(text: str, cap: int) -> tuple[str, str]:
    """`(cleaned, cut to cap)`: the two differ exactly when the cap cut something."""
    cleaned = _clean(text)
    return cleaned, cleaned[:cap]


def _field(text: str) -> str:
    return _continued(_clean(text)[:FIELD_CAP])


def _files(files: Sequence[str]) -> str:
    names = ", ".join(_continued(_clean(name)) for name in files[:FILES_SHOWN])
    hidden = len(files) - FILES_SHOWN
    return f"{names} and {hidden} more" if hidden > 0 else names


def _head_values(facts: StopFacts) -> list[str]:
    return [
        facts.project,
        facts.repository,
        facts.folder,
        facts.story_id or "",
        facts.row_label or "",
    ]


def _head_lines(facts: StopFacts, values: list[str]) -> tuple[str, ...]:
    project, repository, folder, story_id, label = (_continued(value) for value in values)
    lines = [
        f"Run needs you · {project} / {repository} · {facts.park_kind} · stop {facts.park_seq}"
    ]
    if folder:
        lines.append(f"Initiative: {folder}")
    if facts.epic is not None:
        lines.append(f"Epic: {facts.epic}")
    if story_id:
        lines.append(f"Story: {story_id}")
    if label:
        lines.append(f"Row: {label}")
    return tuple(lines)


def _link_line(run_url: str | None) -> list[str]:
    return [f"Run: {run_url}"] if run_url else []


def _render(body: _Body) -> str:
    lines = list(body.head)
    if body.question:
        lines.append(f"Question: {_continued(body.question)}")
    if body.view:
        lines.append(f"Senior's view: {_continued(body.view)}")
    if body.answers:
        lines.append("Earlier answers in this story:")
        lines += [f"- {answer.who}: {_continued(answer.text)}" for answer in body.answers]
    if body.cut:
        lines.append(CUT_MARKER)
    return "\n".join([*lines, *body.tail])


def _fit(body: _Body) -> _Body:
    """The body cut, in the pinned order, until its text is within `MAX_POST_CHARS`."""
    if len(_render(body)) <= MAX_POST_CHARS:
        return body
    body = replace(body, cut=True)
    while body.answers and len(_render(body)) > MAX_POST_CHARS:
        body = replace(body, answers=body.answers[1:])
    body = replace(body, view=_shortened(body, body.view))
    body = replace(body, question=_shortened(body, body.question))
    return body


def _shortened(body: _Body, text: str) -> str:
    """`text` cut from its end by the overflow; a rendered line is never shorter than its raw
    text, so one cut of the overflow is enough for that field."""
    overflow = len(_render(body)) - MAX_POST_CHARS
    if overflow <= 0:
        return text
    return text[: max(len(text) - overflow, 0)]
