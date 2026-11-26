"""What an initiative's merge-conflict stop offers while its step session is open: the signals
`validate` admits there, `continue` and `retry` included (epic 8 story 4: "Given that stop with
its step session open, then `continue` and `retry` are admitted"). Release review 2026-11-26:
the offer read the senior set and hid both controls."""

from __future__ import annotations

from orchestrator.application.rules.signals import (
    MERGE_SESSION_SIGNALS,
    SENIOR_SESSION_SIGNALS,
    run_admitted_signals,
)
from orchestrator.domain.ids import new_id
from tests.unit.application.writer_fixtures import build_run


def test_an_initiative_merge_session_offers_the_merge_session_signals() -> None:
    run = build_run(
        "needs_you", senior_session=True, park_kind="merge_conflict", initiative_id=new_id()
    )

    assert run_admitted_signals(run, "git.merge") == MERGE_SESSION_SIGNALS


def test_a_merge_conflict_outside_an_initiative_keeps_the_senior_offer() -> None:
    run = build_run("needs_you", senior_session=True, park_kind="merge_conflict")

    assert run_admitted_signals(run, "git.merge") == SENIOR_SESSION_SIGNALS
