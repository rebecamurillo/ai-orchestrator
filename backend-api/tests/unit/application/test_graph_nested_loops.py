"""The template graph of a loop inside a loop (story 2, 2026-11-06, AD-15 amendment)."""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.graph import Graph, build_template_graph
from orchestrator.application.templates.validate import validate
from tests.unit.fakes.templates import FakeTemplateVersionRepository

NESTED = Path(__file__).resolve().parent / "templates" / "fixtures" / "nested"


def graph_of(name: str) -> Graph:
    result = validate(
        (NESTED / f"{name}.yaml").read_text(), templates=FakeTemplateVersionRepository()
    )
    assert result.template is not None, result.errors
    return build_template_graph(result.template)


def edges(graph: Graph) -> set[tuple[str, str]]:
    return {(edge.from_id, edge.to_id) for edge in graph.edges}


def test_a_depth_two_graph_has_two_nested_groups_outer_first() -> None:
    graph = graph_of("depth-2")

    assert [group.id for group in graph.groups] == ["epics", "epics.stories"]
    assert "epics.stories.build" in graph.groups[0].members
    assert graph.groups[1].members == ("epics.stories.build",)


def test_the_inner_loop_is_entered_and_left_by_its_neighbours() -> None:
    graph = graph_of("depth-2-pre-post")

    assert ("epics.pre", "epics.stories.build") in edges(graph)
    assert ("epics.stories.after", "epics.post") in edges(graph)
    assert ("epics.pre", "epics.post") not in edges(graph)
    assert "epics.stories.after" in {node.id for node in graph.nodes}


def test_the_outer_group_holds_every_node_inside_it() -> None:
    graph = graph_of("depth-2-pre-post")

    assert graph.groups[0].members == (
        "epics.pre",
        "epics.stories.build",
        "epics.stories.after",
        "epics.post",
    )


def test_a_depth_one_graph_keeps_its_single_group() -> None:
    graph = graph_of("depth-1")

    assert [group.id for group in graph.groups] == ["stories"]
    assert [node.id for node in graph.nodes] == ["stories.build"]


def test_a_depth_zero_graph_has_no_group() -> None:
    assert graph_of("depth-0").groups == ()
