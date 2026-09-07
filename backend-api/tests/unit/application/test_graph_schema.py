"""`application/graph_schema.py` — the shape `build_template_graph` and `build_run_graph`
both build (split out of `application/graph.py` on line count alone; see its own module
docstring). What is asserted here is the part neither builder's own test would think to
check: the defaults a Template's graph relies on being exactly the ones a bare `Node`/
`Group` construction gives.
"""

from __future__ import annotations

from orchestrator.application.graph_schema import Edge, Graph, Group, Node, NodeCall


def test_a_bare_node_carries_no_run_graph_colouring() -> None:
    node = Node(id="a", kind="shell", label="a", gate="deterministic")

    assert node.status is None
    assert node.token is None
    assert node.current is False


def test_a_bare_group_carries_no_status() -> None:
    group = Group(id="stories", label="stories", members=("stories.a",))

    assert group.status is None
    assert group.kind == "for_each"


def test_a_node_call_is_a_plain_name_and_version() -> None:
    call = NodeCall(name="story", version=1)

    assert call.name == "story"
    assert call.version == 1


def test_an_empty_graph_has_three_empty_tuples() -> None:
    graph = Graph()

    assert graph.nodes == ()
    assert graph.edges == ()
    assert graph.groups == ()


def test_an_edge_is_from_and_to_by_the_python_names() -> None:
    edge = Edge(from_id="a", to_id="b")

    assert edge.from_id == "a"
    assert edge.to_id == "b"
