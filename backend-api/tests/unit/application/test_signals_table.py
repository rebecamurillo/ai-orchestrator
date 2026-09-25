"""`application/rules/signals_table.py` — the table half, and the seam it was split on (6.7).

`rules/signals.py` was at 397 of its 400 lines when this story had to add the terminal
narrowing to `run_admitted_signals`, so the table (`Rule`, its predicates, its text builders,
`VALID`, `INVALID` and the two payload readers) moved to a module of its own. Two things
have to stay true for that to be a split rather than a rewrite, and both are asserted here:

1. **Every public name is still reachable where it always was.** `apply_step_result.py`
   imports `REBASELINE_FAILED` from `rules.signals`; `signal_run.py` imports `Rule`;
   `signal_effects.py` calls `signals.accepted_files` and `signals.raised_budget`. A name
   that stopped resolving would fail those modules' own imports, but only the ones a test
   happens to exercise — so the re-export is asserted as an identity, name by name.
2. **The two modules hold one table between them, not two.** `rules.signals.VALID` and
   `signals_table.VALID` must be the same object.

The terminal narrowing itself — the behaviour this story added while it was in there — is
asserted at the bottom, against every state a Run with a terminal session can be in.
"""

from __future__ import annotations

import pytest

from orchestrator.application.rules import signals, signals_table
from orchestrator.domain.statuses import SIGNAL_KINDS, RunStatus
from tests.unit.application.writer_fixtures import build_run

#: Every name `signals_table.py` owns and `signals.py` re-exports, so an import that moved
#: is a failure here rather than in whichever module happened to be loaded first.
RE_EXPORTED = (
    "ACCEPTED",
    "ACCEPTED_SEPARATOR",
    "ANSWER_KEY",
    "ANY_PARK",
    "BUDGET_KEY",
    "BUDGET_RAISED",
    "BUDGET_TOO_LOW",
    "FILES_KEY",
    "INVALID",
    "NON_TERMINAL",
    "PARKED",
    "REBASELINE_FAILED",
    "VALID",
    "Rule",
    "accepted_files",
    "raised_budget",
)


@pytest.mark.parametrize("name", RE_EXPORTED)
def test_every_public_name_of_the_table_is_still_reachable_off_rules_signals(name: str) -> None:
    assert getattr(signals, name) is getattr(signals_table, name)


def test_the_two_modules_share_one_table_object() -> None:
    """Not "equal": a copy would drift the moment either side gained a row."""
    assert signals.VALID is signals_table.VALID
    assert tuple(signals_table.VALID) == SIGNAL_KINDS


def test_the_questions_stayed_behind_and_the_table_does_not_answer_them() -> None:
    """The seam itself: `validate`/`admitted_signals`/`record_text`/`row_at` are questions
    asked *of* the table, and none of them moved into it."""
    for question in (
        "validate",
        "admitted_signals",
        "run_admitted_signals",
        "record_text",
        "row_at",
    ):
        assert hasattr(signals, question)
        assert not hasattr(signals_table, question)


def test_the_table_imports_nothing_from_the_questions_module() -> None:
    """The split is one-directional, which is what keeps it from being an import cycle."""
    source = signals_table.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "rules.signals import" not in text
    assert "rules import signals" not in text


# ── the terminal narrowing (6.7, FR-21) ──────────────────────────────────────


def test_a_terminal_session_offers_cancel_and_release_and_nothing_else() -> None:
    run = build_run(
        "needs_you",
        park_kind="blocked",
        park_path="stories[0].build",
        park_reason="intent gap",
        terminal_session=True,
    )

    assert signals.run_admitted_signals(run, "agent") == ("cancel", "terminal_release")


def test_the_same_stop_without_a_session_offers_its_own_actions() -> None:
    """The control: the narrowing is the session's doing, not the park kind's."""
    run = build_run(
        "needs_you", park_kind="blocked", park_path="stories[0].build", park_reason="intent gap"
    )

    offered = signals.run_admitted_signals(run, "agent")

    # story 1 (2026-09-25): skip_step admitted on every park kind.
    assert offered == ("answer", "skip_step", "skip_story", "skip_epic", "cancel")
    assert "terminal_release" not in offered


@pytest.mark.parametrize("status", ["queued", "running", "needs_you"])
def test_the_narrowing_is_read_before_the_status_tests(status: RunStatus) -> None:
    """`terminal_start` is admitted only while `needs_you`, but `terminal_release` is
    admitted in every non-terminal status — so the answer must not depend on which status a
    Run with the flag set happens to be in."""
    run = build_run(status, terminal_session=True)

    assert signals.run_admitted_signals(run, None) == ("cancel", "terminal_release")


@pytest.mark.parametrize("status", ["done", "failed", "cancelled"])
def test_a_terminal_run_still_offers_nothing_even_with_the_flag_set(status: RunStatus) -> None:
    """A Run that ended is over: AD-13 admits no signal at all, session or no session."""
    run = build_run(status, terminal_session=True)

    assert signals.run_admitted_signals(run, None) == ()


def test_release_is_never_offered_by_the_stop_table_itself() -> None:
    """`Rule.operator_action` stays `False` for the terminal kinds: flipping it would put a
    Release on every stop, including the ones with no session to release."""
    for kind in ("terminal_start", "terminal_release", "terminal_resume"):
        assert signals_table.VALID[kind].operator_action is False
    for park_kind, _ in ((kind, None) for kind in signals_table.ANY_PARK):
        assert "terminal_release" not in signals.admitted_signals(park_kind, "agent")
