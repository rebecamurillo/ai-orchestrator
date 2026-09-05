"""`build_template_graph` — a Template version's nodes, its flags, and its ids (3.4, AD-15).

The loop construct has a module of its own (`test_graph_loops.py`); what is asserted here is
the flat shape, the three gate cases, who is `human`, the `unvalidated` join, and the id rule.

The id rule is asserted as a property over every graph this module builds rather than as a
value per template: no `[`, no `]`, no segment that is only digits. That is what makes an id
joinable and stable across items, and an index creeping in is exactly the regression a
per-template expectation would let through in the template it did not cover.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from orchestrator.application.graph import (
    UNVALIDATED,
    Edge,
    Graph,
    Group,
    NodeCall,
    build_template_graph,
)
from orchestrator.application.steps import AGENT_KIND, CHECKPOINT_KIND
from tests.unit.application.graph_cases import (
    FLAT,
    GATELESS,
    PAUSE_AFTER,
    PAUSE_BEFORE,
    edge_pairs,
    graph_of,
    loop,
    node,
    node_ids,
    templates,
    validated,
)
from tests.unit.fakes.templates import FakeTemplateVersionRepository

__all__ = ["templates"]

# --- a flat template: file order, one chain, no groups --------------------------------------


def test_a_flat_template_is_its_steps_in_file_order(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(FLAT, templates)

    assert node_ids(graph) == ("one", "two", "three")


def test_a_flat_template_chains_every_step_and_declares_no_group(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(FLAT, templates)

    assert edge_pairs(graph) == (("one", "two"), ("two", "three"))
    assert graph.groups == ()


def test_a_step_that_calls_nothing_carries_no_call(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(FLAT, templates)

    assert all(found.call is None for found in graph.nodes)


def test_a_nodes_label_is_its_step_id_and_its_kind_is_the_resolved_kind(
    templates: FakeTemplateVersionRepository,
) -> None:
    """`run:` is sugar for `shell`, so the node's kind is the kind, not the spelling."""
    graph = graph_of(FLAT, templates)

    assert node(graph, "three").label == "three"
    assert node(graph, "three").kind == "shell"


def test_only_a_uses_agent_step_is_flagged_as_an_agent(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(FLAT, templates)

    assert node(graph, "two").kind == AGENT_KIND
    assert node(graph, "two").agent is True
    assert node(graph, "two").gate == "liveness"
    assert [found.id for found in graph.nodes if found.agent] == ["two"]


def test_a_deterministic_step_is_neither_an_agent_nor_a_human_gate(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(FLAT, templates)

    assert node(graph, "one").agent is False
    assert node(graph, "one").human is False
    assert node(graph, "one").gate == "deterministic"


# --- the unvalidated join --------------------------------------------------------------------


def test_a_step_that_declared_no_gate_reads_unvalidated(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(GATELESS, templates)

    assert node(graph, "bare").gate == UNVALIDATED
    assert node(graph, "items.inner").gate == UNVALIDATED


def test_every_unvalidated_path_is_a_node_id_byte_for_byte(
    templates: FakeTemplateVersionRepository,
) -> None:
    """The one property 3.5 and 3.6 join on: no translation between the two lists."""
    result = validated(GATELESS, templates)
    assert result.template is not None
    graph = build_template_graph(result.template)

    assert result.unvalidated == ("bare", "pause", "items.inner")
    assert set(result.unvalidated) <= set(node_ids(graph))
    for path in result.unvalidated:
        assert node(graph, path).gate == UNVALIDATED


def test_a_gate_is_never_filled_in_from_the_kinds_default(
    templates: FakeTemplateVersionRepository,
) -> None:
    """`git.sync`'s `gate_default` is `deterministic`; a gateless step must not read green."""
    graph = graph_of(GATELESS, templates)

    assert node(graph, "bare").gate != "deterministic"


# --- who is human ------------------------------------------------------------------------------


def test_an_explicit_checkpoint_step_is_human_by_kind_and_unvalidated_by_gate(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(GATELESS, templates)
    pause = node(graph, "pause")

    assert pause.kind == CHECKPOINT_KIND
    assert pause.human is True
    assert pause.gate == UNVALIDATED


def test_a_human_gate_on_a_step_of_any_kind_is_human(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(GATELESS, templates)
    ask = node(graph, "ask")

    assert ask.kind == "shell"
    assert ask.gate == "human"
    assert ask.human is True


def test_nothing_else_is_human(templates: FakeTemplateVersionRepository) -> None:
    graph = graph_of(GATELESS, templates)

    assert [found.id for found in graph.nodes if found.human] == ["pause", "ask"]


# --- the id rule (AD-15), as a property over every graph this module builds ---------------------


@pytest.mark.parametrize(
    "text",
    [FLAT, GATELESS, loop(), loop(PAUSE_BEFORE + PAUSE_AFTER)],
    ids=["flat", "gateless", "loop", "loop-both-pauses"],
)
def test_no_id_carries_an_index(text: str, templates: FakeTemplateVersionRepository) -> None:
    graph = graph_of(text, templates)
    ids = [*node_ids(graph), *(group.id for group in graph.groups)]

    for found in ids:
        assert "[" not in found and "]" not in found, found
        assert not any(segment.isdigit() for segment in found.split(".")), found


# --- the values are frozen ---------------------------------------------------------------------


def test_a_node_is_frozen_so_a_caller_cannot_edit_the_graph_it_was_handed(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(FLAT, templates)

    with pytest.raises(PydanticValidationError):
        graph.nodes[0].id = "renamed"  # type: ignore[misc]


def test_the_other_graph_values_are_frozen_too() -> None:
    edge = Edge(from_id="a", to_id="b")
    group = Group(id="items", label="items", members=("items.call",))
    call = NodeCall(name="leaf", version=1)
    graph = Graph()

    with pytest.raises(PydanticValidationError):
        edge.to_id = "c"  # type: ignore[misc]
    with pytest.raises(PydanticValidationError):
        group.members = ()  # type: ignore[misc]
    with pytest.raises(PydanticValidationError):
        call.version = 2  # type: ignore[misc]
    with pytest.raises(PydanticValidationError):
        graph.nodes = ()  # type: ignore[misc]
