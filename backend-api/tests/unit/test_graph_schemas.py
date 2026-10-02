"""`GraphOut` — the wire shape of a graph (3.4).

The one thing that cannot be read off the model class is the edge's field names: `from` is a
Python keyword, so the application value calls them `from_id`/`to_id` and the schema aliases
them back. The browser reads `{from, to}`, and the generated types (AD-3) are derived from
this document, so the alias is asserted on the JSON and on the JSON Schema rather than only
on the model.
"""

from __future__ import annotations

from orchestrator.api.schemas.graph import EdgeOut, GraphOut, GroupOut, NodeCallOut, NodeOut
from orchestrator.application.graph import Edge, Graph, Group, Node, NodeCall

GRAPH = Graph(
    nodes=(
        Node(id="checkout", kind="git.worktree", label="checkout", gate="deterministic"),
        Node(
            id="stories.story",
            kind="template",
            label="story@1",
            gate=None,
            call=NodeCall(name="story", version=1),
        ),
        Node(
            id="stories.after",
            kind="checkpoint",
            label="after",
            gate="human",
            human=True,
        ),
        Node(id="bare", kind="git.sync", label="bare", gate="unvalidated"),
        Node(id="build", kind="agent", label="build", gate="liveness", agent=True),
    ),
    edges=(
        Edge(from_id="checkout", to_id="stories.story"),
        Edge(from_id="stories.story", to_id="stories.after"),
    ),
    groups=(Group(id="stories", label="stories", members=("stories.story", "stories.after")),),
)


def test_of_maps_every_node_edge_and_group_in_order() -> None:
    out = GraphOut.of(GRAPH)

    assert [node.id for node in out.nodes] == [
        "checkout",
        "stories.story",
        "stories.after",
        "bare",
        "build",
    ]
    assert [(edge.from_id, edge.to_id) for edge in out.edges] == [
        ("checkout", "stories.story"),
        ("stories.story", "stories.after"),
    ]
    assert [group.id for group in out.groups] == ["stories"]
    assert out.groups[0].members == ["stories.story", "stories.after"]


def test_a_group_carries_its_label_and_its_construct_onto_the_wire() -> None:
    """3.6 draws the dashed box from this alone; the label is what it writes on it."""
    body = GraphOut.of(GRAPH).model_dump(by_alias=True)

    assert body["groups"] == [
        {
            "id": "stories",
            "label": "stories",
            "kind": "for_each",
            "members": ["stories.story", "stories.after"],
        }
    ]


def test_an_edge_is_serialised_as_from_and_to() -> None:
    body = GraphOut.of(GRAPH).model_dump(by_alias=True)

    assert body["edges"] == [
        {"from": "checkout", "to": "stories.story"},
        {"from": "stories.story", "to": "stories.after"},
    ]


def test_an_edge_declares_from_and_to_in_its_json_schema() -> None:
    """AD-3: the browser's types come from this document, so the alias has to be in it."""
    schema = EdgeOut.model_json_schema(by_alias=True)

    assert set(schema["properties"]) == {"from", "to"}
    assert set(schema["required"]) == {"from", "to"}


def test_an_edge_can_still_be_built_from_the_python_field_names() -> None:
    """`.of()` maps `from_id`/`to_id` across; a schema that refused them would not compile."""
    assert EdgeOut(from_id="a", to_id="b").model_dump(by_alias=True) == {"from": "a", "to": "b"}


def test_a_node_carries_its_flags_its_gate_and_its_label() -> None:
    out = GraphOut.of(GRAPH)
    by_id = {node.id: node for node in out.nodes}

    assert by_id["build"].agent is True
    assert by_id["build"].gate == "liveness"
    assert by_id["stories.after"].human is True
    assert by_id["stories.after"].label == "after"
    assert by_id["bare"].gate == "unvalidated"


def test_a_call_is_carried_across_and_absent_everywhere_else() -> None:
    out = GraphOut.of(GRAPH)
    by_id = {node.id: node for node in out.nodes}

    assert by_id["stories.story"].call == NodeCallOut(name="story", version=1)
    assert by_id["stories.story"].gate is None
    assert by_id["checkout"].call is None


def test_an_empty_graph_is_three_empty_lists_never_null() -> None:
    body = GraphOut.of(Graph()).model_dump(by_alias=True)

    assert body == {"nodes": [], "edges": [], "groups": []}


def test_the_wire_models_are_the_lists_the_browser_reads() -> None:
    """Lists, not tuples: JSON has one sequence, and the generated types say `Array`."""
    out = GraphOut.of(GRAPH)

    assert isinstance(out.nodes, list)
    assert isinstance(out.edges, list)
    assert isinstance(out.groups, list)
    assert isinstance(out.nodes[0], NodeOut)
    assert isinstance(out.groups[0], GroupOut)


def test_a_call_node_of_an_unpinned_call_carries_a_null_version() -> None:
    out = NodeCallOut.of(NodeCall(name="story", version=None))

    assert out.model_dump() == {"name": "story", "version": None}
