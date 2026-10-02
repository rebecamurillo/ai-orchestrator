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

`GraphTextIn` (3.6) is the one *input* here: the YAML `POST /templates/{name}/graph` draws
from. It subclasses `ValidateIn` for the reason `SaveVersionIn` does — the same one field,
under the same length cap, with a distinct name for a distinct route, so the generated
TypeScript names the body a caller actually posts rather than reusing another route's.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.api.schemas.templates import ValidateIn
from orchestrator.application.graph import Edge, Graph, Group, Node, NodeCall, NodeGate


class NodeCallOut(BaseModel):
    """The callee a collapsed `uses: template` node names."""

    name: str
    version: Annotated[
        int | None, Field(description="`null` for an unpinned call (`name@latest`).")
    ]

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


class GraphTextIn(ValidateIn):
    """`POST /templates/{name}/graph`. Same one field; a distinct name for a distinct route."""


# ── the run graph (4.12, SPEC CAP-12) ─────────────────────────────────────────────────────
#
# A second, wider wire shape rather than new fields on `NodeOut`/`GroupOut` above: both are
# pinned by exact-dict equality in `tests/unit/test_graph_schemas.py` and
# `tests/unit/test_graph_router.py` (`body["groups"] == [{four keys exactly}]`), and FastAPI
# serialises every declared field of a `response_model` whether or not it is `None` — so any
# field added there, populated or not, is a fifth key neither test expects and neither test
# names 4.12 as what replaces. `application/graph.py`'s `Node`/`Group` are still the one
# schema `build_template_graph` and `build_run_graph` both build (the brief's own "reuse the
# Graph schema"); only the wire projection of it forks here.


class RunNodeOut(BaseModel):
    """One row of a Run, as one box of the run graph — `NodeOut` plus its live state."""

    id: Annotated[str, Field(description="`step_run.path`, verbatim — the join key (AD-15).")]
    kind: str
    label: str
    gate: NodeGate | None
    agent: bool
    human: bool
    call: NodeCallOut | None
    #: `StepStatus` on a row's own node; `RunStatus` on the one root node (SPEC CAP-12).
    status: str | None
    #: The token the UI renders; sent, never derived (Consistency Conventions).
    token: str | None
    #: True on the running row, or the parked row while nothing is running.
    current: bool

    @classmethod
    def of(cls, node: Node) -> RunNodeOut:
        return cls(
            id=node.id,
            kind=node.kind,
            label=node.label,
            gate=node.gate,
            agent=node.agent,
            human=node.human,
            call=None if node.call is None else NodeCallOut.of(node.call),
            status=node.status,
            token=node.token,
            current=node.current,
        )


class RunGroupOut(BaseModel):
    """One `epics[i]`/`epics[i].stories[j]` frame — `GroupOut` plus its computed status."""

    id: str
    label: str
    kind: Literal["for_each"]
    members: list[str]
    #: By the one rule (`application/graph.py::group_status`); `None` for a cancelled Run.
    status: str | None
    #: k = members with status == "done"; n = members with status != "skipped" (story 1-5).
    #: default_factory (not a literal) keeps the JSON schema free of a "default" key, which
    #: makes openapi-typescript v7 emit `k?: number` (optional) rather than `k: number`
    #: (required). This lets existing test fixtures omit k/n without TypeScript errors.
    k: int = Field(default_factory=lambda: 0)
    n: int = Field(default_factory=lambda: 0)

    @classmethod
    def of(cls, group: Group) -> RunGroupOut:
        return cls(
            id=group.id,
            label=group.label,
            kind=group.kind,
            members=list(group.members),
            status=group.status,
            k=group.k,
            n=group.n,
        )


class RunGraphOut(BaseModel):
    """`GET /runs/{run_id}/graph`. Three lists, never `null` — same shape as `GraphOut`."""

    nodes: list[RunNodeOut]
    edges: list[EdgeOut]
    groups: list[RunGroupOut]

    @classmethod
    def of(cls, graph: Graph) -> RunGraphOut:
        return cls(
            nodes=[RunNodeOut.of(node) for node in graph.nodes],
            edges=[EdgeOut.of(edge) for edge in graph.edges],
            groups=[RunGroupOut.of(group) for group in graph.groups],
        )
