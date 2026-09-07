"""The shape both graphs share: `Node`, `Edge`, `Group`, `Graph` (AD-15, SPEC CAP-12).

Split out of `application/graph.py` on line count alone (`backend-api/AGENTS.md`'s 400-line
module limit) — not a layering change. `build_template_graph` (3.4) and `build_run_graph`
(4.12) both stay in `graph.py`, importing these names from here exactly as any other caller
does, so "the two graphs cannot drift" (Epic 3's hand-off) is still true: one `Node`, one
`Group`, one `Graph`, wherever the class body happens to live.

`Node.status`/`.token`/`.current` and `Group.status` are the run graph's own fields
(SPEC CAP-12): `None`/`False` on a Template's graph, which has no execution to point at.
`Node.status`/`.token` carry two alphabets depending on which graph and which node — a run
graph's per-row nodes carry a `StepStatus`/step token, its one synthetic root node a
`RunStatus`/Run token instead, because a `Node` is one row of one diagram, never two, and
`RunStatus` has `cancelled`, which no `StepStatus` does.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from orchestrator.application.steps import Gate

#: What a node's `gate` reads when the step declared none (NFR-2). Never `gate_default`: a
#: step nobody gated is not silently the kind's normal gate. The word is on screen, not green.
UNVALIDATED: Literal["unvalidated"] = "unvalidated"

#: A node's gate: what the file declared, or the word for "the file declared nothing".
NodeGate = Gate | Literal["unvalidated"]

#: The gate a person answers. A step carrying it is `human` whatever its kind is.
HUMAN_GATE: Gate = "human"

#: What joins the segments of a node id. One separator, no indices (AD-15).
SEPARATOR = "."

#: The last segment of each synthetic item checkpoint, and its label.
BEFORE_ITEM = "before"
AFTER_ITEM = "after"

#: The one construct a `Group` can be in this release (AD-15: one `for_each` per file).
FOR_EACH: Literal["for_each"] = "for_each"


class NodeCall(BaseModel):
    """The callee a collapsed `uses: template` node names. Never expanded here."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: int


class Node(BaseModel):
    """One box of the diagram, and one row of the Template screen's step list."""

    model_config = ConfigDict(frozen=True)

    #: The template-relative dotted path, index-free — joinable to `unvalidated`. A run
    #: graph's node id is `step_run.path` instead, indices and all (AD-15).
    id: str
    #: The step kind, resolved: `run:` sugar is `shell`, a call is `template`.
    kind: str
    #: The step id, or `{name}@{version}` for a call.
    label: str
    #: What the file declared, `unvalidated` where it declared nothing, `None` for a call.
    gate: NodeGate | None = None
    #: True iff the step dispatches a harness.
    agent: bool = False
    #: True iff a person decides this step: the `human` gate, or the `checkpoint` kind.
    human: bool = False
    #: The callee, for a collapsed call and for nothing else.
    call: NodeCall | None = None
    #: The run graph's own colouring (module docstring); `None` on a Template's graph.
    status: str | None = None
    #: The token the UI renders beside `status`; sent, never derived client-side.
    token: str | None = None
    #: True on the running row, or the parked row while none is running (SPEC CAP-12).
    current: bool = False


class Edge(BaseModel):
    """One arrow: the id it leaves, the id it enters. Rendered `{from, to}` on the wire."""

    model_config = ConfigDict(frozen=True)

    from_id: str
    to_id: str


class Group(BaseModel):
    """One `for_each` (template graph) or one `epics[i]`/`epics[i].stories[j]` frame (run
    graph), and the ordered node ids drawn inside its box."""

    model_config = ConfigDict(frozen=True)

    id: str
    #: The loop's id, or the frame's own prefix: the group has no name of its own to carry.
    label: str
    #: The one construct a group can be. A field rather than an assumption, because Epic 4
    #: draws a group per callee frame beside these and the two have to be told apart.
    kind: Literal["for_each"] = FOR_EACH
    members: tuple[str, ...] = ()
    #: A run-graph group's status, by the one rule (`graph.py::group_status`); `None` on a
    #: Template's graph, and `None` for every group of a `cancelled` Run (nothing ran to
    #: completion or to a stop, so no member status is a fact worth colouring).
    status: str | None = None


class Graph(BaseModel):
    """A Template's or a Run's shape. No layout: 3.6 draws it, `Node`/`Group` colour it."""

    model_config = ConfigDict(frozen=True)

    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    groups: tuple[Group, ...] = ()
