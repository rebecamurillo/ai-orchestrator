"""`FakeLogFacts` reads the result envelope the fake harness prints."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness.fake.facts import NO_ENVELOPE, FakeLogFacts

TOKENS_IN = 10
TOKENS_OUT = 4


def an_attempt(**over: object) -> Attempt:
    fields = {"id": new_id(), "run_id": new_id(), "step_run_id": new_id(), "n": 1}
    return Attempt(status="done", **{**fields, **over})  # type: ignore[arg-type]


def test_an_envelope_with_usage_is_three_harness_rows(tmp_path: Path) -> None:
    log = tmp_path / "a.log"
    envelope = {
        "type": "result",
        "total_cost_usd": "0.25",
        "usage": {"input_tokens": TOKENS_IN, "output_tokens": TOKENS_OUT},
    }
    log.write_text(f"noise\n{json.dumps(envelope)}\n")

    facts = FakeLogFacts().extract(an_attempt(model="m-1"), str(log))

    assert facts.status == "ok"
    rows = {u.usage_class: u for u in facts.usage}
    assert set(rows) == {"input_uncached", "output", "money"}
    assert rows["input_uncached"].tokens == TOKENS_IN
    assert rows["output"].tokens == TOKENS_OUT
    assert rows["money"].usd == Decimal("0.25")
    assert {(u.source, u.model, u.conversation) for u in facts.usage} == {
        ("harness", "m-1", "main")
    }


def test_a_log_without_an_envelope_is_partial_and_names_why(tmp_path: Path) -> None:
    log = tmp_path / "a.log"
    log.write_text("nothing printed\n")

    facts = FakeLogFacts().extract(an_attempt(), str(log))

    assert (facts.status, facts.reason, facts.usage) == ("partial", NO_ENVELOPE, ())


def test_a_model_less_attempt_is_named_fake(tmp_path: Path) -> None:
    log = tmp_path / "a.log"
    log.write_text(
        json.dumps(
            {
                "type": "result",
                "total_cost_usd": 0,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )
    )
    facts = FakeLogFacts().extract(an_attempt(), str(log))
    assert {u.model for u in facts.usage} == {"fake"}
