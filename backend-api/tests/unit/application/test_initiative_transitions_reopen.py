"""`reopen_round_steps` (epic 9 story 2, AC2): the conversation steps a reopened round runs."""

from __future__ import annotations

from orchestrator.application.rules.initiative_transitions import reopen_round_steps
from orchestrator.domain.entities.project_package import StepDecl
from tests.unit.application.initiative_transition_world import spec_steps


def test_the_round_runs_the_step_and_every_later_step_not_done() -> None:
    steps = spec_steps()

    assert reopen_round_steps(steps, {"intake", "product"}, "ux") == ("ux", "tech")


def test_a_later_step_done_in_an_earlier_round_is_left_out() -> None:
    steps = spec_steps()

    assert reopen_round_steps(steps, {"intake", "product", "tech"}, "ux") == ("ux",)


def test_a_forced_skip_is_not_done_so_later_steps_that_are_done_stay_out_only_by_done() -> None:
    steps = spec_steps()

    assert reopen_round_steps(steps, {"tech"}, "product") == ("product", "ux")


def test_the_reopened_step_is_listed_even_when_it_was_done() -> None:
    assert reopen_round_steps(spec_steps(), {"tech"}, "tech") == ("tech",)


def test_the_gate_and_non_conversation_steps_are_never_listed() -> None:
    extra = StepDecl(id="note", kind="automatic", skill=None, persona=None, file=None, writes=())
    steps = (*spec_steps()[:2], extra, *spec_steps()[2:])

    assert reopen_round_steps(steps, set(), "intake") == ("intake", "product", "ux", "tech")
