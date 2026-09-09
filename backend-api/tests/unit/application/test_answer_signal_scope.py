"""`answer` through `handle_signal`, now that SPEC CAP-1 (6.1) has an effect for it.

`test_handle_signal.py` proves the scope gate itself — what is in and what is still refused.
This module is the Answer's own coverage, and it is deliberately wider than the single
assertion it replaced: the gate record AD-13 requires, the text the Operator typed landing on
it verbatim, the 409 the story's own fourth acceptance criterion names, and the kinds that
have *not* landed keeping their refusal — because "answer works now" must not quietly read
as "the scope gate stopped refusing things".
"""

from __future__ import annotations

import pytest

from orchestrator.application.rules.signals import ANSWER_KEY
from orchestrator.application.use_cases.signals import handle_signal
from orchestrator.domain.errors import Conflict
from orchestrator.domain.values import Signal
from tests.unit.application.test_handle_signal import (
    BUILD,
    CHECKPOINT_ROW,
    effect_ports,
    parked,
    send,
)

ANSWER = "Post to the project's channel only"

# ── what the Answer records ─────────────────────────────────────────────────────────────


def test_the_gate_record_is_an_answer_by_the_operator_carrying_the_text_verbatim() -> None:
    """AD-13: every signal is written to the gate record. The Answer's own words are the
    record's text — `rules/signals.py` gives the rule `text_key=ANSWER_KEY` for exactly this
    — and they are also what the resumed dispatch quotes back to the harness (FR-18)."""
    world = parked("blocked", BUILD, "blocked")

    send(world, effect_ports(world), "answer", **{ANSWER_KEY: ANSWER})

    answers = world.records()
    written = [record for record in answers if record.event == "answer"]
    assert len(written) == 1
    assert written[0].actor == "operator"
    assert written[0].text == ANSWER
    assert written[0].payload[ANSWER_KEY] == ANSWER


def test_an_answer_with_no_text_still_records_the_tables_own_sentence() -> None:
    """`record_text` falls back to the rule's phrase; a record is never left blank."""
    world = parked("blocked", BUILD, "blocked")

    send(world, effect_ports(world), "answer")

    assert [record.text for record in world.records() if record.event == "answer"] == [
        "answer from the operator"
    ]


def test_an_answer_at_a_spec_checkpoint_is_admitted_on_the_agent_row_too() -> None:
    """AD-13 admits `answer` on `{blocked, checkpoint}` — 6.2 sends a Reject as this signal."""
    world = parked("checkpoint", BUILD, "checkpoint")

    outcome = send(world, effect_ports(world), "answer", **{ANSWER_KEY: "re-plan it"})

    assert world.status_of(BUILD) == "queued"
    assert outcome.run.status == "running"


# ── what it is still refused on ─────────────────────────────────────────────────────────


def test_an_answer_on_a_timeout_park_is_ad13s_own_409() -> None:
    """The story's fourth acceptance criterion, and the reason the refusal text matters: a
    `timeout` is not an intent gap, so there is no question on disk to answer."""
    world = parked("timeout", BUILD, "error")

    with pytest.raises(Conflict, match="signal answer invalid for status needs_you"):
        send(world, effect_ports(world), "answer", **{ANSWER_KEY: ANSWER})

    assert world.status_of(BUILD) == "error"
    assert world.records() == []


def test_an_answer_on_a_row_that_is_not_an_agent_is_refused() -> None:
    """`row_kinds={agent}`: a checkpoint row's own stop is 6.2's Continue, not an Answer."""
    world = parked("checkpoint", CHECKPOINT_ROW, "checkpoint")

    with pytest.raises(Conflict, match="signal answer invalid"):
        send(world, effect_ports(world), "answer", **{ANSWER_KEY: ANSWER})


@pytest.mark.parametrize(
    ("park_kind", "path", "row_status", "kind", "payload"),
    [
        ("budget", BUILD, "blocked", "budget_raise", {"budget_usd": "50"}),
    ],
    ids=["budget_raise"],
)
def test_the_kinds_this_story_did_not_land_still_answer_not_available_yet(
    park_kind: str, path: str, row_status: str, kind: str, payload: dict[str, object]
) -> None:
    """Widening the scope gate for one kind must not widen it for the rest: 6.4, 6.5 and 6.6
    each land their own, and until they do the refusal is what an Operator gets."""
    world = parked(park_kind, path, row_status)

    with pytest.raises(Conflict, match=f"{kind} not available yet"):
        send(world, effect_ports(world), kind, **payload)

    assert world.engine.calls == []


def test_an_answer_on_a_running_run_never_reaches_the_scope_gate_at_all() -> None:
    """`validate` runs first and unconditionally, so a Run that is not parked gets AD-13's
    own sentence rather than this module's — the order `handle_signal` is built on."""
    world = parked("blocked", BUILD, "blocked")
    running = world.stored_run().model_copy(update={"status": "running", "park_kind": None})
    world.ports.runs.update(running)

    with pytest.raises(Conflict, match="signal answer invalid for status running"):
        handle_signal(
            effect_ports(world), world.run.id, Signal(kind="answer", payload={ANSWER_KEY: ANSWER})
        )
