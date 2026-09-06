"""The shape of one Template version: its nodes, its edges, its loop groups (AD-15).

Pure over `ParsedTemplate`. Nothing here reads YAML, re-implements a validator rule, or
performs I/O: `validate()` already read the file, and a second reading is exactly how the
diagram and the validator would come to disagree. Kind facts come from
`application/steps` — the one enumeration there is (AD-9).

**The node id.** A top-level step is its own `id`; a step inside a `for_each` is
`{loop_id}.{step_id}`; a synthetic item checkpoint is `{loop_id}.before` or
`{loop_id}.after`. No index, ever. That is what makes an id byte-identical to the paths
`validate()` reports in `ValidationResult.unvalidated` — the two lists join with no
translation — and stable across the items a loop expands into.

AD-15 illustrates the id with `stories.story.build`, which is three segments and therefore
a path through a callee. That is the *run* graph's id (`step_run.path`, the expanded rows);
the template graph collapses a call, so its deepest id is two segments, `{loop}.{step}` —
which is also exactly the deepest path `validate()` emits. Said here rather than picked
silently: the spine's example is the same dotted, index-free form at the other surface, not
a second id rule.

**A call is one node.** A `uses: template` step is collapsed: it names its callee and stops
there. Its gate is `None`, because a call has no gate of its own; the callee's own steps
carry theirs. The consequence is deliberate and is not closed here: a gateless step inside
`story@1` is invisible in `epic@1`'s graph, exactly as it is invisible in `epic@1`'s
`ValidationResult`. The `unvalidated` guarantee is per file, not per expanded plan; Epic 4's
planner owns the expanded view.

**Why the walker builds edges in this order.** Each top-level entry is reduced to a frame:
its nodes, its internal edges, its entry id and its exit id. The connecting edge from the
previous frame's exit is appended *before* the frame's own internal edges, which is what
makes `epic@1` read `baseline->stories.story` and then `stories.story->stories.after` —
the order a left-to-right reader expects. A loop frame's ordered members are
`[before?] + inner steps + [after?]`, so a `pause_before_item_when` moves the incoming edge
onto `.before` and a `pause_after_item_when` moves the outgoing edge off `.after` with no
special case at the call site, and the group holds that same ordered list: an item-level
pause belongs inside the box a diagram draws around the loop.

A validated tree never holds an empty `steps:` list — the key table rejects both the root's
and a loop's — so a frame always has a first and a last node.

`_nodes_for_step` is the seam Epic 4 reuses: in this release a step is exactly one node, and
`build_run_graph` expands one planned step into one row per item. Returning a tuple the
walker chains is what lets that arrive without changing the walker.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict

from orchestrator.application.steps import (
    AGENT_KIND,
    CHECKPOINT_KIND,
    KIND_META,
    TEMPLATE_CALL_KIND,
    Gate,
)
from orchestrator.application.templates.model import ForEach, ParsedTemplate, Step

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

    #: The template-relative dotted path, index-free — joinable to `unvalidated`.
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


class Edge(BaseModel):
    """One arrow: the id it leaves, the id it enters. Rendered `{from, to}` on the wire."""

    model_config = ConfigDict(frozen=True)

    from_id: str
    to_id: str


class Group(BaseModel):
    """One `for_each`, and the ordered node ids drawn inside its box."""

    model_config = ConfigDict(frozen=True)

    id: str
    #: The loop's id: the group has no name of its own to carry.
    label: str
    #: The one construct a group can be. A field rather than an assumption, because Epic 4
    #: draws a group per callee frame beside these and the two have to be told apart.
    kind: Literal["for_each"] = FOR_EACH
    members: tuple[str, ...] = ()


class Graph(BaseModel):
    """A Template version's shape. No layout, no status: 3.6 draws it, Epic 4 colours it."""

    model_config = ConfigDict(frozen=True)

    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    groups: tuple[Group, ...] = ()


@dataclass(frozen=True)
class _Frame:
    """One top-level entry reduced: what it draws, and where a neighbour attaches to it."""

    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    group: Group | None = None

    @property
    def entry(self) -> str:
        """The id the previous entry's edge enters."""
        return self.nodes[0].id

    @property
    def exit(self) -> str:
        """The id the next entry's edge leaves."""
        return self.nodes[-1].id


def build_template_graph(parsed: ParsedTemplate) -> Graph:
    """The graph of one Template file: its steps in file order, chained, loops grouped."""
    nodes: list[Node] = []
    edges: list[Edge] = []
    groups: list[Group] = []
    previous: str | None = None
    for entry in parsed.steps:
        frame = _frame(entry)
        nodes.extend(frame.nodes)
        if previous is not None:
            edges.append(Edge(from_id=previous, to_id=frame.entry))
        edges.extend(frame.edges)
        if frame.group is not None:
            groups.append(frame.group)
        previous = frame.exit
    return Graph(nodes=tuple(nodes), edges=tuple(edges), groups=tuple(groups))


def _frame(entry: Step | ForEach) -> _Frame:
    """One top-level entry — a step or the one loop construct — as a frame."""
    if isinstance(entry, ForEach):
        return _loop_frame(entry)
    nodes = _nodes_for_step(entry, prefix=None)
    return _Frame(nodes=nodes, edges=_chain(tuple(node.id for node in nodes)))


def _loop_frame(loop: ForEach) -> _Frame:
    """`[before?] + inner steps + [after?]`, chained, and grouped under the loop's id."""
    nodes: list[Node] = []
    if loop.pause_before_item_when is not None:
        nodes.append(_item_checkpoint(loop.id, BEFORE_ITEM))
    for step in loop.steps:
        nodes.extend(_nodes_for_step(step, prefix=loop.id))
    if loop.pause_after_item_when is not None:
        nodes.append(_item_checkpoint(loop.id, AFTER_ITEM))
    members = tuple(node.id for node in nodes)
    return _Frame(
        nodes=tuple(nodes),
        edges=_chain(members),
        group=Group(id=loop.id, label=loop.id, members=members),
    )


def _nodes_for_step(step: Step, *, prefix: str | None) -> tuple[Node, ...]:
    """The nodes one planned step draws — exactly one in this release.

    The seam Epic 4's `build_run_graph` reuses: an expanded Run draws one row per item, so
    this returns a tuple the walker chains rather than a single node it positions.
    """
    return (_node(step, _node_id(step.id, prefix)),)


def _node_id(step_id: str, prefix: str | None) -> str:
    """A step's id, under the enclosing loop's id where there is one. Never an index."""
    if prefix is None:
        return step_id
    return f"{prefix}{SEPARATOR}{step_id}"


def _node(step: Step, node_id: str) -> Node:
    call = _call_of(step)
    return Node(
        id=node_id,
        kind=step.uses,
        label=f"{call.name}@{call.version}" if call is not None else step.id,
        gate=_gate_of(step),
        agent=step.uses == AGENT_KIND,
        human=_is_human(step),
        call=call,
    )


def _item_checkpoint(loop_id: str, position: str) -> Node:
    """The stop a `pause_*_item_when` declares: one node per item, inside the loop's box.

    The operator wrote the pause, so the gate is the `checkpoint` kind's own — read from
    `KIND_META`, not spelled out here — and never `unvalidated`: nothing was left ungated.
    """
    return Node(
        id=f"{loop_id}{SEPARATOR}{position}",
        kind=CHECKPOINT_KIND,
        label=position,
        gate=KIND_META[CHECKPOINT_KIND].gate_default,
        human=True,
    )


def _call_of(step: Step) -> NodeCall | None:
    """The callee of a collapsed call; `None` for every step that calls nothing."""
    if step.call is None:
        return None
    return NodeCall(name=step.call.name, version=step.call.version)


def _gate_of(step: Step) -> NodeGate | None:
    """What the file declared, `unvalidated` where it declared nothing, `None` for a call.

    The three cases are exactly the three `validate()` distinguishes, which is what lets the
    `unvalidated` list and this field agree without either consulting the other. The call is
    tested first, not last: the key table accepts `gate` on a `uses: template` step, and a
    call whose author wrote one is still a call — it is a path segment, not a row, so there
    is no gate for it to carry (AD-15).
    """
    if step.uses == TEMPLATE_CALL_KIND:
        return None
    if step.gate is not None:
        return step.gate
    return UNVALIDATED


def _is_human(step: Step) -> bool:
    """A person decides this step: it declared the `human` gate, or it is a checkpoint.

    A call is neither, whatever it declared: nobody stops at a path segment.
    """
    if step.uses == TEMPLATE_CALL_KIND:
        return False
    return step.gate == HUMAN_GATE or step.uses == CHECKPOINT_KIND


def _chain(ids: Sequence[str]) -> tuple[Edge, ...]:
    """One edge per consecutive pair; nothing at all for a single node."""
    return tuple(Edge(from_id=before, to_id=after) for before, after in pairwise(ids))
