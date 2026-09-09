"""`budget_raise` through `handle_signal` (story 6-6, SPEC CAP-6, FR-17, AD-11, AD-13).

Until this story the kind was refused `budget_raise not available yet` after `validate`
passed — the scope gate `use_cases/signals.py::_in_scope` draws. The writer 4.5 built is
reached here for the first time, so what is asserted is AD-13's own four outcomes end to
end: the two park rows that hold the Run where it is, the two that resume it, and the
refusal a figure that does not clear the spend earns.

The resume half is `test_budget_raise_resume.py`'s; this module owns the Run-level facts.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from orchestrator.application.rules.signals import BUDGET_KEY
from orchestrator.application.use_cases.signals import SignalEffectPorts, handle_signal
from orchestrator.domain.errors import Conflict
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
AFTER = "stories[1].after"
WORK_DIR = "/work"


def parked(row_status: str, path: str = BUILD, **over: object) -> World:
    """A Run stopped `budget` on one row — `test_signal_run.py`'s own shape."""
    fields: dict[str, object] = {
        "park_kind": "budget",
        "park_path": path,
        "park_reason": "budget $9.00 / $5.00",
        "spend_usd": Decimal("9"),
        "budget_usd": Decimal("5"),
    }
    fields.update(over)
    return a_world("needs_you", EPIC_PLAN, {path: row_status}, **fields)


def ports_for(world: World) -> SignalEffectPorts:
    return SignalEffectPorts(
        signal=world.signal_ports,
        git=FakeGit(),
        process=FakeProcessRunner(),
        work_dir=WORK_DIR,
        read_environment=lambda _run_id: None,
    )


def engine_calls(world: World) -> list[str]:
    return [name for name, _ in world.engine.calls]


def raise_to(world: World, amount: str) -> object:
    signal = Signal(kind="budget_raise", payload={BUDGET_KEY: amount})
    return handle_signal(ports_for(world), world.run.id, signal)


def test_a_raise_over_a_blocked_row_keeps_the_run_parked_at_that_row() -> None:
    """AC1: `budget_usd` is written, `park_kind` becomes the row's own status, the Run stays
    `needs_you`, and no engine signal is sent — so the next poll shows the Question again."""
    world = parked("blocked")

    outcome = raise_to(world, "60")

    stored = world.stored_run()
    assert stored.budget_usd == Decimal("60")
    assert (stored.status, stored.park_kind) == ("needs_you", "blocked")
    assert stored.park_reason == "budget $9.00 / $5.00"
    assert engine_calls(world) == []
    assert outcome.resumed is False  # type: ignore[attr-defined]


def test_a_raise_over_a_checkpoint_row_keeps_it_the_same_way() -> None:
    world = parked("checkpoint", AFTER)

    raise_to(world, "60")

    stored = world.stored_run()
    assert (stored.status, stored.park_kind) == ("needs_you", "checkpoint")
    assert engine_calls(world) == []


def test_a_raise_over_a_done_row_resumes_the_run() -> None:
    world = parked("done")

    raise_to(world, "60")

    stored = world.stored_run()
    assert stored.status == "running"
    assert (stored.park_kind, stored.park_path, stored.park_reason) == (None, None, None)
    assert engine_calls(world) == ["signal"]


def test_the_record_names_the_new_figure_rather_than_the_operator() -> None:
    """The brief's own voice: `budget raised to ${new}`, at two decimal places."""
    world = parked("blocked")

    raise_to(world, "60")

    record = world.records()[-1]
    assert (record.event, record.actor) == ("budget_raise", "operator")
    assert record.text == "budget raised to $60.00"


def test_a_figure_that_does_not_clear_the_spend_is_refused_with_the_spend() -> None:
    """AC3: `budget_usd: 30` against `spend_usd: 41.20` is a 409 that says which is which."""
    world = parked("blocked", spend_usd=Decimal("41.20"))

    with pytest.raises(Conflict, match=r"new budget must exceed spend \$41\.20"):
        raise_to(world, "30")

    assert world.stored_run().budget_usd == Decimal("5")
    assert world.records() == []
    assert engine_calls(world) == []


def test_a_budget_raise_on_a_park_it_is_not_admitted_on_keeps_ad13s_own_sentence() -> None:
    """`extra_refusal` is only the *extra*'s refusal: a wrong park is the table's own 409,
    because there it is the park that is wrong and not the figure."""
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {BUILD: "error"},
        park_kind="timeout",
        park_path=BUILD,
        park_reason="timeout",
        spend_usd=Decimal("9"),
    )

    with pytest.raises(Conflict, match="signal budget_raise invalid for status needs_you"):
        raise_to(world, "60")
