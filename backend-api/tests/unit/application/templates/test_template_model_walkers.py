"""`all_steps` and `all_loops` at every depth (story 2, 2026-11-06, AD-15 amendment)."""

from __future__ import annotations

from orchestrator.application.templates.model import ForEach, Step, all_loops, all_steps
from tests.unit.application.templates.test_template_model import a_step


def loop(ident: str, *steps: Step | ForEach) -> ForEach:
    return ForEach(line=1, id=ident, source="x", as_name=ident, steps=steps)


def test_a_flat_list_yields_its_steps() -> None:
    entries = (a_step(id="a"), a_step(id="b"))

    assert [step.id for step in all_steps(entries)] == ["a", "b"]
    assert list(all_loops(entries)) == []


def test_one_loop_deep_is_walked_in_file_order() -> None:
    entries = (a_step(id="a"), loop("l", a_step(id="b")), a_step(id="c"))

    assert [step.id for step in all_steps(entries)] == ["a", "b", "c"]
    assert [each.id for each in all_loops(entries)] == ["l"]


def test_two_loops_deep_yields_outer_loops_first() -> None:
    entries = (loop("outer", a_step(id="a"), loop("inner", a_step(id="b")), a_step(id="c")),)

    assert [step.id for step in all_steps(entries)] == ["a", "b", "c"]
    assert [each.id for each in all_loops(entries)] == ["outer", "inner"]
