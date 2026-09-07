"""`Gateway`, `AttemptSpend`, `ModelSpend` — shape, frozen-ness, and `FakeGateway`'s fit.

TDD first (AD-18): written before `domain/ports/gateway.py` existed.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.domain.ports.gateway import AttemptSpend, Gateway, ModelSpend
from tests.unit.fakes.gateway import FakeGateway

RUN_ID = UUID("00000000-0000-0000-0000-0000000000c1")
ATTEMPT_ID = UUID("00000000-0000-0000-0000-0000000000c2")


def test_model_spend_is_frozen() -> None:
    spend = ModelSpend(model="gpt-5", usd=Decimal("1.50"), tokens_in=10, tokens_out=5)

    assert spend.model == "gpt-5"
    with pytest.raises(FrozenInstanceError):
        spend.usd = Decimal("2")  # type: ignore[misc]


def test_attempt_spend_is_frozen_and_carries_a_model_breakdown() -> None:
    by_model = (ModelSpend(model="gpt-5", usd=Decimal("1.50"), tokens_in=10, tokens_out=5),)
    spend = AttemptSpend(
        usd=Decimal("1.50"),
        tokens_in=10,
        tokens_out=5,
        by_model=by_model,
        calls=1,
        provisional=False,
    )

    assert spend.by_model == by_model
    assert spend.provisional is False
    with pytest.raises(FrozenInstanceError):
        spend.usd = Decimal("0")  # type: ignore[misc]


def test_fake_gateway_satisfies_the_gateway_protocol() -> None:
    fake = FakeGateway()

    assert isinstance(fake, Gateway)


def test_an_unscripted_pair_answers_provisional_zero() -> None:
    fake = FakeGateway()

    spend = fake.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend.provisional is True
    assert spend.usd == Decimal("0")
    assert spend.tokens_in == 0
    assert spend.tokens_out == 0
    assert spend.by_model == ()
    assert spend.calls == 0
    assert fake.calls == [(RUN_ID, ATTEMPT_ID)]


def test_a_scripted_pair_answers_what_was_scripted() -> None:
    fake = FakeGateway()
    scripted = AttemptSpend(
        usd=Decimal("4.20"),
        tokens_in=100,
        tokens_out=50,
        by_model=(ModelSpend(model="gpt-5", usd=Decimal("4.20"), tokens_in=100, tokens_out=50),),
        calls=2,
        provisional=False,
    )
    fake.script(RUN_ID, ATTEMPT_ID, scripted)

    spend = fake.spend_for_attempt(RUN_ID, ATTEMPT_ID)

    assert spend is scripted
