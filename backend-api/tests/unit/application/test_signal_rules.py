"""`application/rules/signals.py` — AD-13's validity table, read both ways.

`admitted_signals` is asserted against PRD §4.6's *Signals admitted* column, transcribed
below a second time: AD-13 calls that table "the reason-text and admitted-signal contract",
so the rules are compared with it rather than with themselves.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from orchestrator.application.rules.signals import (
    ANSWER_KEY,
    BUDGET_KEY,
    FILES_KEY,
    VALID,
    accepted_files,
    admitted_signals,
    raised_budget,
    record_text,
    validate,
)
from orchestrator.domain.errors import Conflict
from orchestrator.domain.statuses import PARK_KINDS, SIGNAL_KINDS, ParkKind, SignalKind
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import (
    EPIC_PLAN,
    INITIATIVE_PLAN,
    build_rows,
    build_run,
)

#: PRD §4.6, transcribed: `park_kind -> (park row kind, the actions the stop offers)`.
STOPS: dict[ParkKind, tuple[str, tuple[SignalKind, ...]]] = {
    # PRD §4.6, story 1 (2026-09-25): `skip_step` added to all 11 park-kind entries.
    "blocked": ("agent", ("answer", "skip_step", "skip_story", "skip_epic", "cancel")),
    "checkpoint": (
        "agent",
        ("answer", "continue", "skip_step", "skip_story", "skip_epic", "cancel"),
    ),
    "verify_failed": ("shell", ("retry", "skip_step", "skip_story", "skip_epic", "cancel")),
    "budget": ("agent", ("skip_step", "budget_raise", "cancel")),
    "timeout": ("shell", ("retry", "skip_step", "skip_story", "skip_epic", "cancel")),
    "push_rejected": ("git.push", ("retry", "skip_step", "skip_epic", "cancel")),
    "protected_path": (
        "agent",
        ("continue", "retry", "skip_step", "skip_story", "skip_epic", "cancel"),
    ),
    "misconfigured": ("agent", ("retry", "skip_step", "skip_story", "skip_epic", "cancel")),
    "plan_stale": ("plan.check", ("continue", "skip_step", "cancel")),
    "internal": ("agent", ("retry", "skip_step", "skip_story", "skip_epic", "cancel")),
    # Added 2026-09-23 (multi-repository initiative, story S4): AD-13's amended park list —
    # `merge_conflict` originally admitted `retry` and `cancel` only; story 1 (2026-09-25)
    # adds `skip_step` (admitted on every park kind, no exclusions).
    "merge_conflict": ("git.merge", ("retry", "skip_step", "cancel")),
}


def a_row(kind: str = "agent", status: str = "blocked") -> object:
    rows = build_rows(build_run().id)
    row = next(entry for entry in rows if entry.kind == kind)
    return row.model_copy(update={"status": status})


def parked(park_kind: ParkKind = "blocked", path: str = "stories[0].build", **over: object):
    return build_run("needs_you", park_kind=park_kind, park_path=path, park_reason="why", **over)


# ── the table itself ─────────────────────────────────────────────────────────


def test_every_signal_kind_has_exactly_one_rule() -> None:
    assert tuple(VALID) == SIGNAL_KINDS


@pytest.mark.parametrize("park_kind", sorted(STOPS))
def test_a_stop_offers_the_actions_prd_4_6_lists(park_kind: ParkKind) -> None:
    row_kind, expected = STOPS[park_kind]

    assert set(admitted_signals(park_kind, row_kind)) == set(expected)


def test_a_done_checkpoint_row_offers_no_answer_because_a_reject_is_spec_only() -> None:
    """PRD §4.6: *Reject with a reason (spec only)* — a spec checkpoint is an `agent` row."""
    assert "answer" not in admitted_signals("checkpoint", "checkpoint")
    assert "continue" in admitted_signals("checkpoint", "checkpoint")


def test_the_terminal_kinds_are_not_offered_as_operator_actions() -> None:
    """They are driven by the browser and the poll job, not by a button on the stop."""
    offered = {kind for park in PARK_KINDS for kind in admitted_signals(park, "agent")}

    assert not offered & {"terminal_start", "terminal_release", "terminal_resume"}


# ── validate: the valid cases ────────────────────────────────────────────────


def test_an_answer_on_a_blocked_agent_row_is_admitted() -> None:
    assert validate(parked(), a_row("agent", "blocked"), Signal(kind="answer")) is VALID["answer"]


def test_a_cancel_is_admitted_on_a_run_that_never_parked() -> None:
    assert validate(build_run("running"), None, Signal(kind="cancel")) is VALID["cancel"]


def test_a_budget_raise_above_the_spend_is_admitted() -> None:
    run = parked("budget", spend_usd=Decimal("3"))
    signal = Signal(kind="budget_raise", payload={BUDGET_KEY: "4"})

    assert validate(run, a_row("agent", "blocked"), signal) is VALID["budget_raise"]


def test_a_skip_epic_on_a_one_epic_run_is_admitted_without_an_epics_frame() -> None:
    """Operator decision 2026-09-30: no template name hardcoded in product code. "The whole
    Run is one epic" is now the *plan's* shape — a Story loop and nothing above it — so the
    rows are handed to `validate` and the Template's name says nothing."""
    run = parked("blocked", path="stories[0].build", template_name="house-epic")
    rows = build_rows(run.id, EPIC_PLAN)

    assert validate(run, a_row(), Signal(kind="skip_epic"), rows) is VALID["skip_epic"]


def test_a_skip_epic_outside_an_epic_frame_of_a_multi_epic_run_is_refused() -> None:
    """The other half of the same fact, which the old name test could not state: a plan that
    *does* group Stories into epics is not one epic, so a stop with no `epics[n]` under it has
    nothing for this signal to skip."""
    run = parked("blocked", path="plan", template_name="house-epic")
    rows = build_rows(run.id, INITIATIVE_PLAN)

    with pytest.raises(Conflict):
        validate(run, a_row(), Signal(kind="skip_epic"), rows)


def test_a_skip_epic_inside_an_epics_frame_is_admitted() -> None:
    run = parked("blocked", path="epics[0].stories[0].build", template_name="house-initiative")
    rows = build_rows(run.id, INITIATIVE_PLAN)

    assert validate(run, a_row(), Signal(kind="skip_epic"), rows) is VALID["skip_epic"]


def test_a_terminal_start_is_admitted_while_no_session_is_open() -> None:
    assert validate(parked(), a_row(), Signal(kind="terminal_start")) is VALID["terminal_start"]


def test_a_terminal_release_is_admitted_only_inside_a_session() -> None:
    run = parked(terminal_session=True)

    assert validate(run, a_row(), Signal(kind="terminal_release")) is VALID["terminal_release"]


def test_a_terminal_resume_needs_a_session_and_a_blocked_row() -> None:
    run = parked(terminal_session=True)

    assert validate(run, a_row(), Signal(kind="terminal_resume")) is VALID["terminal_resume"]


# ── validate: one refusal per column ─────────────────────────────────────────


def refused(run: object, row: object, kind: SignalKind) -> str:
    with pytest.raises(Conflict) as raised:
        validate(run, row, Signal(kind=kind))  # type: ignore[arg-type]
    return str(raised.value)


def test_a_signal_to_a_run_in_the_wrong_status_is_refused_naming_both() -> None:
    message = refused(build_run("running"), None, "retry")

    assert message == "signal retry invalid for status running / park None"


def test_a_signal_the_park_kind_does_not_admit_is_refused() -> None:
    assert "invalid for status needs_you / park plan_stale" in refused(
        parked("plan_stale", path="plan"), a_row("plan.check", "error"), "retry"
    )


def test_an_answer_on_a_row_that_is_not_an_agent_row_is_refused() -> None:
    row = a_row("checkpoint", "checkpoint")

    assert "signal answer" in refused(parked("checkpoint"), row, "answer")


def test_an_answer_with_no_parked_row_at_all_is_refused() -> None:
    assert "signal answer" in refused(parked(), None, "answer")


def test_a_terminal_resume_onto_a_row_that_is_not_blocked_is_refused() -> None:
    run = parked(terminal_session=True)

    assert "signal terminal_resume" in refused(run, a_row("agent", "checkpoint"), "terminal_resume")


def test_a_terminal_resume_with_no_parked_row_is_refused() -> None:
    run = parked(terminal_session=True)

    assert "signal terminal_resume" in refused(run, None, "terminal_resume")


def test_a_terminal_resume_outside_a_session_is_refused() -> None:
    assert "signal terminal_resume" in refused(parked(), a_row(), "terminal_resume")


def test_a_second_terminal_start_inside_a_session_is_refused() -> None:
    run = parked(terminal_session=True)

    assert "signal terminal_start" in refused(run, a_row(), "terminal_start")


def test_a_skip_story_on_a_park_outside_a_story_frame_is_refused() -> None:
    assert "signal skip_story" in refused(parked(path="baseline"), a_row(), "skip_story")


def test_a_skip_story_on_a_run_with_no_park_path_is_refused() -> None:
    run = build_run("needs_you", park_kind="blocked", park_path=None)

    assert "signal skip_story" in refused(run, None, "skip_story")


def test_a_skip_epic_on_an_initiative_with_no_epic_frame_is_refused() -> None:
    run = parked(path="stories[0].build", template_name="initiative")

    assert "signal skip_epic" in refused(run, a_row(), "skip_epic")


def test_a_skip_epic_on_an_initiative_with_no_park_path_is_refused() -> None:
    run = build_run("needs_you", park_kind="blocked", park_path=None, template_name="initiative")

    assert "signal skip_epic" in refused(run, None, "skip_epic")


def test_a_run_parked_with_no_kind_at_all_admits_nothing() -> None:
    """`needs_you` without a `park_kind` is not a stop the table describes."""
    run = build_run("needs_you", park_path="stories[0].build")

    assert "signal retry" in refused(run, a_row("shell", "error"), "retry")


@pytest.mark.parametrize(
    "payload",
    [{}, {BUDGET_KEY: "not a number"}, {BUDGET_KEY: "1"}, {BUDGET_KEY: "NaN"}],
)
def test_a_budget_raise_that_does_not_exceed_the_spend_is_refused(payload: dict[str, str]) -> None:
    run = parked("budget", spend_usd=Decimal("3"))

    with pytest.raises(Conflict):
        validate(run, a_row(), Signal(kind="budget_raise", payload=payload))


def test_a_budget_raise_of_something_that_is_not_a_number_at_all_is_refused() -> None:
    run = parked("budget", spend_usd=Decimal("3"))

    with pytest.raises(Conflict):
        validate(run, a_row(), Signal(kind="budget_raise", payload={BUDGET_KEY: None}))


# ── what the record says ─────────────────────────────────────────────────────


def test_an_answers_own_words_are_the_record() -> None:
    assert record_text(VALID["answer"], {ANSWER_KEY: "use the other adapter"}) == (
        "use the other adapter"
    )


def test_an_empty_answer_falls_back_to_the_fixed_phrase() -> None:
    assert record_text(VALID["answer"], {ANSWER_KEY: ""}) == "answer from the operator"


def test_a_kind_that_carries_no_text_uses_its_fixed_phrase() -> None:
    assert record_text(VALID["retry"], {}) == "retried by the operator"


def test_the_validated_budget_comes_back_as_a_decimal() -> None:
    assert raised_budget({BUDGET_KEY: "12.50"}) == Decimal("12.50")


def test_the_accepted_files_come_back_in_the_order_they_arrived() -> None:
    assert accepted_files({FILES_KEY: ["a.py", "b.py"]}) == ("a.py", "b.py")


def test_a_continue_that_accepted_nothing_carries_no_files() -> None:
    assert accepted_files({}) == ()


def test_a_files_payload_that_is_not_a_list_accepts_nothing() -> None:
    """A bare string would otherwise be spread one character per accepted file."""
    assert accepted_files({FILES_KEY: "a.py"}) == ()


def test_an_infinite_budget_is_refused_rather_than_accepted_as_unbounded() -> None:
    run = parked("budget", spend_usd=Decimal("3"))

    with pytest.raises(Conflict):
        validate(run, a_row(), Signal(kind="budget_raise", payload={BUDGET_KEY: "Infinity"}))


# ── skip_step: story 1, 2026-09-25 behaviour change ──────────────────────────


def test_a_skip_step_is_admitted_on_every_non_dependency_park_kind() -> None:
    """AD-13, ratified 2026-09-25: park_kinds=ANY_PARK (story 1)."""
    non_dep = [pk for pk in PARK_KINDS if pk != "dependency"]
    for park_kind in non_dep:
        assert "skip_step" in admitted_signals(park_kind, "agent"), (
            f"expected skip_step for {park_kind}"
        )


def test_a_skip_step_on_a_dependency_park_is_refused() -> None:
    """Dependency parks have no park_row (park_path=None); row_statuses check refuses it."""
    run = build_run("needs_you", park_kind="dependency", park_path=None)

    assert "invalid for status needs_you / park dependency" in refused(run, None, "skip_step")


def test_a_skip_step_on_a_done_row_is_refused() -> None:
    """row_statuses={blocked,checkpoint,error}; a `done` row is outside that set."""
    run = parked("budget")
    row = a_row("agent", "done")

    assert "invalid for status needs_you / park budget" in refused(run, row, "skip_step")
