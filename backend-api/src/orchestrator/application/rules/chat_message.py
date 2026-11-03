"""The words `chat_poll` posts (story 3-3, AD-25): a stop's thread, its reminder, and the
one-line notice of a senior's test-edit acceptance. Pure: no port, no I/O.

No platform syntax lives here. Each adapter renders its own mentions and neutralises its own
markup; this module only writes plain lines and keeps untrusted text from starting one.

**Untrusted text** (a question, a senior's view, an answer, a notice's files and reason) can
hold anything an agent or a person wrote. Every `Cc` character but `\\n` and every bidi
control is dropped, then each continuation line is prefixed with `CONTINUATION`, so such
text never opens a line, a fence, a heading or a quote. The facts this system wrote itself
go through the same cleaning, since a label or a folder can echo a file an agent wrote.

A single-line fact (project, repository, folder, story id, label) has its newlines collapsed
to spaces, so it never takes a continuation line.

**Length** is counted in code points, as the adapter will render it: each rule takes a
`measure`, which the passes bind to `ChatChannel.rendered_length` (escaping, neutralisation
and the mention prefix included), so the rule stays pure. Each field has its cap; the whole
post is then held to `MAX_POST_CHARS` by cutting whole answer lines oldest first, then the
senior's view from its end, then the question from its end. Whatever was cut, `CUT_MARKER`
stands once on its own line before the action line, and the action line and the Run link
always stay.

**The Run link is the post's trusted suffix**, never its text: it is this system's own line,
so an adapter appends it as written rather than neutralising it, and an IPv6 literal stays a
link (story 3-3 lead review of the build, 2026-11-02).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Sequence
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
class ChatPost:
    """What a pass sends: `text`, which the adapter neutralises, and `suffix`, which it
    appends as written."""

    text: str
    suffix: str = ""


#: The length an adapter would send a post at (`ChatChannel.rendered_length`, bound).
Measure = Callable[[ChatPost], int]


def plain_length(post: ChatPost) -> int:
    """A post's length with no escaping and no mentions: the default `measure`."""
    return len(post.text) + len(post.suffix)


@dataclass(frozen=True)
class _Body:
    """The parts of a stop's post the total cut may shorten, already cleaned and capped."""

    question: str
    view: str
    answers: tuple[Answer, ...]
    cut: bool
    head: tuple[str, ...]
    tail: tuple[str, ...]
    suffix: str


def run_link(base_url: str, run_id: UUID) -> str | None:
    """The Run's page, `notify/format.py::run_url`'s path, or `None` with no base URL."""
    base = base_url.strip().rstrip("/")
    return f"{base}/workflows/{run_id}" if base else None


def action_line(park_kind: str) -> str:
    return REPLY_ACTION if park_kind == REPLY_STOP else PAGE_ACTION


def chat_author(author: str, platform: str) -> str:
    """Who an answer a thread reply gave is shown as: `{author} via {platform}` (4-1)."""
    return f"{_field(author)} via {_field(platform)}"


def neutralise(text: str) -> str:
    """`text` with its controls dropped and every continuation line prefixed."""
    return _continued(_clean(text))


def compose_stop(
    facts: StopFacts, metadata_only: bool, measure: Measure = plain_length
) -> ChatPost:
    """A stop's thread root: one fact per line, in the pinned order, within the limit."""
    head = [_capped(_one_line(value), FIELD_CAP) for value in _head_values(facts)]
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
        tail=(action_line(facts.park_kind),),
        suffix=_link_suffix(facts.run_url),
    )
    fitted = _fit(body, measure)
    return ChatPost(_render(fitted), fitted.suffix)


def reminder_text(park_kind: str, park_seq: int, hours: int, run_url: str | None) -> ChatPost:
    """A reminder in the stop's thread; `park_kind` is the thread's, as it was at posting."""
    lines = [
        f"Still waiting · {park_kind} · stop {park_seq} · parked {hours} h",
        action_line(park_kind),
    ]
    return ChatPost("\n".join(lines), _link_suffix(run_url))


def accept_line(
    facts: AcceptFacts, metadata_only: bool, measure: Measure = plain_length
) -> ChatPost:
    """The one channel line for a `senior_accept`, within the limit, its link kept."""
    head = f"{_field(facts.project)} / {_field(facts.repository)}"
    if facts.story_id:
        head += f" · story {_field(facts.story_id)}"
    link = f" · {facts.run_url}" if facts.run_url else ""
    if metadata_only:
        return ChatPost(
            f"{head} · the senior accepted test edits to {len(facts.files)} files", link
        )
    body = f"the senior accepted test edits: {_files(facts.files)}"
    reason = _clean(facts.reason)[:REASON_CAP]
    if reason:
        body += f" · {_continued(reason)}"
    return ChatPost(_fitted_line(f"{head} · ", body, link, measure), link)


def _fitted_line(prefix: str, body: str, suffix: str, measure: Measure) -> str:
    """`prefix` and as much of `body` as fits; a suffix that leaves no room drops the body."""
    overflow = measure(ChatPost(prefix + body, suffix)) - MAX_POST_CHARS
    while overflow > 0 and body:
        body = body[: max(len(body) - overflow, 0)]
        overflow = measure(ChatPost(prefix + body, suffix)) - MAX_POST_CHARS
    return prefix + body


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


def _one_line(text: str) -> str:
    return text.replace("\n", " ")


def _field(text: str) -> str:
    return _one_line(_clean(text))[:FIELD_CAP]


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
    project, repository, folder, story_id, label = values
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


def _link_suffix(run_url: str | None) -> str:
    return f"\nRun: {run_url}" if run_url else ""


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


def _overflow(body: _Body, measure: Measure) -> int:
    return measure(ChatPost(_render(body), body.suffix)) - MAX_POST_CHARS


def _fit(body: _Body, measure: Measure) -> _Body:
    """The body cut, in the pinned order, until its rendering is within `MAX_POST_CHARS`."""
    if _overflow(body, measure) <= 0:
        return body
    body = replace(body, cut=True)
    while body.answers and _overflow(body, measure) > 0:
        body = replace(body, answers=body.answers[1:])
    body = replace(body, view=_shortened(body, body.view, measure))
    body = replace(body, question=_shortened(body, body.question, measure))
    return body


def _shortened(body: _Body, text: str, measure: Measure) -> str:
    """`text` cut from its end by the overflow. Every character renders at one code point or
    more, so removing `n` of them removes at least `n` from the rendering, and one cut of the
    overflow is enough for that field."""
    overflow = _overflow(body, measure)
    if overflow <= 0:
        return text
    return text[: max(len(text) - overflow, 0)]
