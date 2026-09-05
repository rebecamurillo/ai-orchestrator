"""The HTTP shape of a graph (3.4): `{nodes, edges, groups}`.

A projection of `application/graph.py` and nothing more — no field here is derived, because
a second derivation is a second answer. Tuples become lists, because JSON has one sequence
type and the generated TypeScript (AD-3) says `Array`.

The edge is the one place the two shapes differ by more than a container. `from` is a Python
keyword, so the application value names its ends `from_id` and `to_id`; the alias puts them
back on the wire as `{from, to}`, which is what a reader of the document — and the diagram
in 3.6 — expects an edge to be called. `populate_by_name` keeps `.of()` able to build one
from the Python names.

Epic 4's run graph extends this schema rather than replacing it: a Run's rows are these
nodes with a status beside them, and the endpoint that serves them is the second route on
`api/routers/graph.py`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.application.graph import Edge, Graph, Group, Node, NodeCall, NodeGate


class NodeCallOut(BaseModel):
    """The callee a collapsed `uses: template` node names."""

    name: str
    version: int

    @classmethod
    def of(cls, call: NodeCall) -> NodeCallOut:
        return cls(name=call.name, version=call.version)


class NodeOut(BaseModel):
    """One step of the Template, as one box of the diagram."""

    id: Annotated[
        str,
        Field(
            description=(
                "The template-relative dotted path, index-free: `{step}`, `{loop}.{step}`, "
                "or `{loop}.before` / `{loop}.after` for an item checkpoint. The same "
                "string `/validate` reports in `unvalidated`."
            )
        ),
    ]
    kind: str
    label: str
    gate: Annotated[
        NodeGate | None,
        Field(
            description=(
                "What the Template declared. `unvalidated` where it declared nothing "
                "(NFR-2); `null` on a template call, which has no gate of its own."
            )
        ),
    ]
    agent: bool
    human: bool
    call: NodeCallOut | None

    @classmethod
    def of(cls, node: Node) -> NodeOut:
        return cls(
            id=node.id,
            kind=node.kind,
            label=node.label,
            gate=node.gate,
            agent=node.agent,
            human=node.human,
            call=None if node.call is None else NodeCallOut.of(node.call),
        )


class EdgeOut(BaseModel):
    """One arrow, keyed `from` and `to` — the names `from_id`/`to_id` stand in for."""

    model_config = ConfigDict(populate_by_name=True)

    from_id: Annotated[str, Field(alias="from")]
    to_id: Annotated[str, Field(alias="to")]

    @classmethod
    def of(cls, edge: Edge) -> EdgeOut:
        return cls(from_id=edge.from_id, to_id=edge.to_id)


class GroupOut(BaseModel):
    """One `for_each`, and the ordered node ids drawn inside its box."""

    id: str
    label: str
    kind: Annotated[
        Literal["for_each"],
        Field(description="The construct the group draws. One value in this release."),
    ]
    members: list[str]

    @classmethod
    def of(cls, group: Group) -> GroupOut:
        return cls(id=group.id, label=group.label, kind=group.kind, members=list(group.members))


class GraphOut(BaseModel):
    """`GET /templates/{name}/{version}/graph`. Three lists, never `null`."""

    nodes: list[NodeOut]
    edges: list[EdgeOut]
    groups: list[GroupOut]

    @classmethod
    def of(cls, graph: Graph) -> GraphOut:
        return cls(
            nodes=[NodeOut.of(node) for node in graph.nodes],
            edges=[EdgeOut.of(edge) for edge in graph.edges],
            groups=[GroupOut.of(group) for group in graph.groups],
        )
