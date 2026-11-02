"""The consult rule (AD-22): which stop is offered to a senior, what the senior decided, and
which record delivers its answer. Pure: no port, no I/O.

**The decision is read from a file, never from model output** (AD-10). The senior writes
`{tree}/.orchestrator/consult/{seq:03d}-{n}.decision.md`: frontmatter `status` and `reason`,
the body is the answer. `.orchestrator/` holds a `.gitignore` of `*`, so neither HEAD nor
`git status` ever sees the folder, and the unchanged-tree check stays exact.

**A `verify_failed` stop is declared by the `run` row** (`on_fail {redispatch, max, consult}`)
and consulted on the redispatch target, whose entry carries the declared block. Its answer
is a diagnosis for one further fresh redispatch (`diagnosis`), never a `delivers` record.

**Everything but a usable answer or an escalation fails closed.** `accept` is a decision
story 1-5 gives a meaning to; until then it is no readable decision, like an answer with an
empty body.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from orchestrator.application.story_file import FRONTMATTER_FENCE, frontmatter
from orchestrator.application.templates.lines import load_with_lines
from orchestrator.application.templates.table import CONSULT_KEY
from orchestrator.domain.entities.attempt import Attempt, agent_attempts
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import ParkKind
from orchestrator.domain.values import ConsultOutcome

#: The entry keys `step_run.consults[kind]` is written with.
STATE_KEY = "state"
QUESTION_KEY = "question"
SNAPSHOT_KEY = "snapshot"
ANSWERED_BY_KEY = "answered_by"
ORPHAN_PGID_KEY = "orphan_pgid"
#: A `verify_failed` entry also carries the block the verify row declared (the target row
#: declares none for that stop) and the verify row's path, where the stop parks.
DECLARED_KEY = "declared"
PARK_PATH_KEY = "park_path"
DUE = "due"
ANSWER: ConsultOutcome = "answer"
ESCALATE: ConsultOutcome = "escalate"
FAILED: ConsultOutcome = "failed"

#: The gate events a consult writes, and the record payload key that names the stop kind.
CONSULT_EVENT = "consult"
SENIOR_ANSWER_EVENT = "senior_answer"
KIND_KEY = "kind"
TEXT_KEY = "text"
VERIFY_FAILED: ParkKind = "verify_failed"

#: Where a verify row's planned consult sits: `with_resolved["on_fail"]["consult"]`.
ON_FAIL_KEY = "on_fail"
CONSULT_BLOCK_KEY = "consult"

#: The planned block's keys, as `templates/consult.py::plan_consult` writes them.
ON_KEY = "on"
PROMPTS_KEY = "prompts"
ANSWER_CLAUSE = "answer"

#: The folder that ignores itself, and the one file in it a consult reads.
IGNORE_FILE = ".orchestrator/.gitignore"
IGNORE_ALL = "*\n"
DECISION_FILE = ".orchestrator/consult/{seq:03d}-{n}.decision.md"

#: What a decision file's frontmatter may say (`accept` is 1-5's).
STATUS_KEY = "status"
REASON_KEY = "reason"
STATUSES = frozenset({ANSWER, "accept", ESCALATE})

#: Every runtime token a consult clause may name; an unknown one stays literal prose.
PLACEHOLDER = re.compile(
    r"\{(skill|spec_folder|story_id|condition|decision|answer|command|code|tail|agent_log)\}"
)


@dataclass(frozen=True)
class Decision:
    """One parsed decision file: everything the walker is allowed to know about it."""

    status: str
    reason: str
    body: str


def declared(with_resolved: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The row's planned `consult` block, or `None` for a row that consults nobody."""
    block = with_resolved.get(CONSULT_KEY)
    return block if isinstance(block, Mapping) else None


def verify_block(with_resolved: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The consult a `run` row's planned `on_fail` redispatch carries, or `None` (story 1-6)."""
    route = with_resolved.get(ON_FAIL_KEY)
    block = route.get(CONSULT_BLOCK_KEY) if isinstance(route, Mapping) else None
    return block if isinstance(block, Mapping) else None


def block_of(with_resolved: Mapping[str, Any], entry: Mapping[str, Any]) -> Mapping[str, Any]:
    """The block a consult runs on: the entry's own when the stop was declared elsewhere (a
    `verify_failed` stop is declared by the verify row), else the row's."""
    own = entry.get(DECLARED_KEY)
    return own if isinstance(own, Mapping) else declared(with_resolved) or {}


def offered(with_resolved: Mapping[str, Any], consults: Mapping[str, Any], kind: str) -> bool:
    """Whether a stop of `kind` goes to a senior: declared, and never consulted on this row."""
    block = declared(with_resolved)
    if block is None or kind in consults:
        return False
    stops = block.get(ON_KEY)
    return isinstance(stops, list) and kind in stops


def due(consults: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]] | None:
    """The `(kind, entry)` an offer left waiting for its consult attempt, or `None`."""
    for kind, entry in consults.items():
        if isinstance(entry, Mapping) and entry.get(STATE_KEY) == DUE:
            return kind, entry
    return None


def decision_path(seq: int, n: int) -> str:
    """The decision file of attempt `n` of row `seq`, relative to the dispatch tree."""
    return DECISION_FILE.format(seq=seq, n=n)


def parse(text: str | None) -> Decision | None:
    """The file as the walker reads it, or `None` for every way it can be unreadable."""
    head = frontmatter(text or "")
    if head is None:
        return None
    loaded = load_with_lines(head)
    if loaded.root is None:
        return None
    status = loaded.root.get(STATUS_KEY)
    if not isinstance(status, str) or status.strip() not in STATUSES:
        return None
    reason = loaded.root.get(REASON_KEY)
    return Decision(
        status=status.strip(),
        reason=reason.strip() if isinstance(reason, str) else "",
        body=_body(text or ""),
    )


def _body(text: str) -> str:
    """Everything after the frontmatter's closing fence, stripped."""
    lines = text.splitlines()
    close = next(n for n in range(1, len(lines)) if lines[n].strip() == FRONTMATTER_FENCE)
    return "\n".join(lines[close + 1 :]).strip()


def verdict(decision: Decision | None) -> tuple[ConsultOutcome, str]:
    """What the decision comes to: the answer's body, the escalation's reason, or nothing."""
    if decision is not None and decision.status == ANSWER and decision.body:
        return ANSWER, decision.body
    if decision is not None and decision.status == ESCALATE:
        return ESCALATE, decision.reason
    return FAILED, ""


def fill(clause: str, values: Mapping[str, str]) -> str:
    """One literal-insertion pass: a value is never re-scanned for tokens of its own."""
    return PLACEHOLDER.sub(lambda match: values.get(match.group(1), match.group(0)), clause)


def answer_text(
    with_resolved: Mapping[str, Any],
    question: str,
    body: str,
    entry: Mapping[str, Any] | None = None,
) -> str:
    """What the agent is sent: the consult's own `answer` clause, filled."""
    block = block_of(with_resolved, entry or {})
    prompts = block.get(PROMPTS_KEY)
    clause = prompts.get(ANSWER_CLAUSE) if isinstance(prompts, Mapping) else None
    if not isinstance(clause, str):
        return body
    return fill(clause, {"condition": question, "answer": body})


def delivers(
    row: StepRun, attempts: Iterable[Attempt], records: Iterable[GateRecord]
) -> GateRecord | None:
    """The row's latest `blocked` `senior_answer` while it is still owed, or `None`.

    Owed while the entry reads `answer` and no `agent` attempt numbered above the consult
    that answered has come back (`end_sha` is written only by the agent's tail). A
    `verify_failed` diagnosis is never delivered as a record: see `diagnosis`.
    """
    return _owed(row, attempts, records, verify=False)


def diagnosis(row: StepRun, attempts: Iterable[Attempt], records: Iterable[GateRecord]) -> str:
    """The senior's diagnosis the row's next fresh redispatch still owes, or `""` (story 1-6).

    Owed on the same terms as `delivers`. It reaches the agent beside the failure text of a
    redispatch, in a new session, never as a message into the row's old one (AD-10).
    """
    found = _owed(row, attempts, records, verify=True)
    return str(found.payload.get(TEXT_KEY, "")) if found is not None else ""


def _owed(
    row: StepRun, attempts: Iterable[Attempt], records: Iterable[GateRecord], *, verify: bool
) -> GateRecord | None:
    answered_by = _answered_by(row.consults, verify)
    if answered_by is None:
        return None
    if any(a.n > answered_by and a.end_sha is not None for a in agent_attempts(attempts)):
        return None
    mine = [
        r
        for r in records
        if r.event == SENIOR_ANSWER_EVENT
        and r.path == row.path
        and (r.payload.get(KIND_KEY) == VERIFY_FAILED) == verify
    ]
    return mine[-1] if mine else None


def _answered_by(consults: Mapping[str, Any], verify: bool) -> int | None:
    for kind, entry in consults.items():
        if (kind == VERIFY_FAILED) != verify:
            continue
        if not isinstance(entry, Mapping) or entry.get(STATE_KEY) != ANSWER:
            continue
        number = entry.get(ANSWERED_BY_KEY)
        if isinstance(number, int):
            return number
    return None
