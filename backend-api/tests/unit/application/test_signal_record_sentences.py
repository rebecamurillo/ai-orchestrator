"""What a gate record says for the two signals whose sentence quotes a value (story 6-6).

`Rule.text`/`Rule.text_key` cover the eight kinds whose record is a fixed phrase or the
Operator's own words verbatim. Two are neither: a raised budget names the *validated* figure
(`budget raised to $60.00`, not the payload's `"60"`), and an Accept names the files it
accepted — while the same `continue` at a checkpoint accepts none and keeps the phrase. That
is what `Rule.text_from` is, and this module is its coverage.

`Rule.extra_refusal` is the same idea for the other direction: `validate` refuses a
`budget_raise` that does not clear the spend with the sentence that says why, while a
`budget_raise` on the wrong park keeps AD-13's own — there it is the park that is wrong.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from orchestrator.application.rules.signals import (
    ANSWER_KEY,
    BUDGET_KEY,
    FILES_KEY,
    VALID,
    record_text,
    validate,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Signal
from tests.unit.fakes.clock import EPOCH


def a_run(**over: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "needs_you",
        "budget_usd": Decimal("10"),
        "created_at": EPOCH,
        "park_kind": "budget",
        "spend_usd": Decimal("41.20"),
    }
    fields.update(over)
    return Run(**fields)  # type: ignore[arg-type]


# ── what the record says ─────────────────────────────────────────────────────


def test_a_raised_budget_names_the_new_figure_at_two_decimal_places() -> None:
    assert record_text(VALID["budget_raise"], {BUDGET_KEY: "60"}) == "budget raised to $60.00"


def test_the_figure_is_the_validated_one_and_not_the_payloads_own_string() -> None:
    """`"60.005"` is a `Decimal` before it is a sentence, so the record reads like money."""
    assert record_text(VALID["budget_raise"], {BUDGET_KEY: "60.005"}) == "budget raised to $60.00"


def test_an_accept_names_the_files_it_accepted_in_the_order_they_arrived() -> None:
    text = record_text(VALID["continue"], {FILES_KEY: ["tests/api/test_runs.py", "AGENTS.md"]})

    assert text == "accepted: tests/api/test_runs.py, AGENTS.md"


def test_a_continue_that_accepted_nothing_keeps_the_fixed_phrase() -> None:
    assert record_text(VALID["continue"], {}) == "continued by the operator"


def test_a_files_payload_that_is_not_a_list_keeps_the_fixed_phrase_too() -> None:
    """`accepted_files`'s own defence: a bare string is not a list of files."""
    assert record_text(VALID["continue"], {FILES_KEY: "a.py"}) == "continued by the operator"


def test_the_kinds_that_never_had_a_builder_are_unchanged() -> None:
    assert record_text(VALID["retry"], {}) == "retried by the operator"
    assert record_text(VALID["answer"], {ANSWER_KEY: "use psycopg"}) == "use psycopg"
    assert record_text(VALID["answer"], {ANSWER_KEY: ""}) == "answer from the operator"


# ── what the refusal says ────────────────────────────────────────────────────


def test_a_budget_that_does_not_clear_the_spend_names_the_spend() -> None:
    signal = Signal(kind="budget_raise", payload={BUDGET_KEY: "30"})

    with pytest.raises(Conflict, match=r"new budget must exceed spend \$41\.20"):
        validate(a_run(), None, signal)


def test_a_budget_that_is_not_a_number_earns_the_same_sentence() -> None:
    signal = Signal(kind="budget_raise", payload={BUDGET_KEY: "not a number"})

    with pytest.raises(Conflict, match="new budget must exceed spend"):
        validate(a_run(), None, signal)


def test_a_budget_raise_on_the_wrong_park_keeps_ad13s_own_sentence() -> None:
    """`extra_refusal` is the *extra*'s refusal only: the columns are checked first, so a
    park the table does not admit is still `signal {kind} invalid for status …`."""
    signal = Signal(kind="budget_raise", payload={BUDGET_KEY: "60"})

    with pytest.raises(Conflict, match="signal budget_raise invalid for status needs_you"):
        validate(a_run(park_kind="timeout"), None, signal)


def test_a_kind_whose_extra_declares_no_sentence_still_gets_the_table_refusal() -> None:
    """`skip_story` has an `extra` (`_has_story_frame`) and no `extra_refusal`."""
    signal = Signal(kind="skip_story")

    with pytest.raises(Conflict, match="signal skip_story invalid"):
        validate(a_run(park_kind="blocked", park_path="push"), None, signal)
