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

A loop inside a loop takes its full index-free path (`epics.stories`, `epics.stories.build`,
`epics.stories.after`), exactly the path `validate()` emits. AD-15 illustrates the id with
`stories.story.build`, a path through a callee: that is the *run* graph's id
(`step_run.path`, the expanded rows); the template graph collapses a call.

**A call is one node.** A `uses: template` step is collapsed: it names its callee and stops
there. Its gate is `None`, because a call has no gate of its own; the callee's own steps
carry theirs. The consequence is deliberate and is not closed here: a gateless step inside
A callee is invisible in its caller's graph, exactly as it is invisible in that caller's
`ValidationResult`. The `unvalidated` guarantee is per file, not per expanded plan; Epic 4's
planner owns the expanded view.

**Why the walker builds edges in this order.** Each entry of a `steps:` list is reduced to a
frame: its nodes, its internal edges, its groups, its entry id and its exit id. The connecting
edge from the previous frame's exit is appended *before* the frame's own internal edges,
which is what makes a caller read `baseline->stories.story` and then
`stories.story->stories.after` — the order a left-to-right reader expects. A loop frame's
ordered members are
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

from orchestrator.application.graph_schema import (
    AFTER_ITEM,
    BEFORE_ITEM,
    FOR_EACH,
    HUMAN_GATE,
    SEPARATOR,
    UNVALIDATED,
    Edge,
    Graph,
    Group,
    Node,
    NodeCall,
    NodeGate,
)
from orchestrator.application.run_graph import (
    ROOT_ID,
    STEP_TOKENS,
    _run_token,  # noqa: F401 - tests read the Board-token rule through `graph`
    build_run_graph,
    group_status,
)
from orchestrator.application.steps import (
    AGENT_KIND,
    CHECKPOINT_KIND,
    KIND_META,
    TEMPLATE_CALL_KIND,
)
from orchestrator.application.templates.model import ForEach, ParsedTemplate, Step

__all__ = [
    "AFTER_ITEM",
    "BEFORE_ITEM",
    "FOR_EACH",
    "HUMAN_GATE",
    "ROOT_ID",
    "SEPARATOR",
    "STEP_TOKENS",
    "UNVALIDATED",
    "Edge",
    "Graph",
    "Group",
    "Node",
    "NodeCall",
    "NodeGate",
    "build_run_graph",
    "build_template_graph",
    "group_status",
]


@dataclass(frozen=True)
class _Frame:
    """One entry of a `steps:` list reduced: what it draws, and where a neighbour attaches."""

    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    groups: tuple[Group, ...] = ()

    @property
    def entry(self) -> str:
        """The id the previous entry's edge enters."""
        return self.nodes[0].id


def build_template_graph(parsed: ParsedTemplate) -> Graph:
    """The graph of one Template file: its steps in file order, chained, loops grouped."""
    frame = _list_frame(parsed.steps, prefix=None)
    return Graph(nodes=frame.nodes, edges=frame.edges, groups=frame.groups)


def _list_frame(entries: Sequence[Step | ForEach], prefix: str | None) -> _Frame:
    """One `steps:` list as a frame: each entry chained to the one before it, in list order."""
    return _chained(
        [
            _loop_frame(entry, prefix) if isinstance(entry, ForEach) else _step_frame(entry, prefix)
            for entry in entries
        ]
    )


def _chained(frames: Sequence[_Frame]) -> _Frame:
    """Frames joined end to entry. The joining edge is appended *before* the next frame's own
    internal edges, so a caller reads `baseline->stories.story` and then
    `stories.story->stories.after`."""
    nodes: list[Node] = []
    edges: list[Edge] = []
    groups: list[Group] = []
    for frame in frames:
        if nodes:
            edges.append(Edge(from_id=nodes[-1].id, to_id=frame.entry))
        nodes.extend(frame.nodes)
        edges.extend(frame.edges)
        groups.extend(frame.groups)
    return _Frame(nodes=tuple(nodes), edges=tuple(edges), groups=tuple(groups))


def _step_frame(step: Step, prefix: str | None) -> _Frame:
    nodes = _nodes_for_step(step, prefix=prefix)
    return _Frame(nodes=nodes, edges=_chain(tuple(node.id for node in nodes)))


def _loop_frame(loop: ForEach, prefix: str | None) -> _Frame:
    """`[before?] + the loop's list + [after?]`, chained, grouped under the loop's full path."""
    path = _node_id(loop.id, prefix)
    body = _list_frame(loop.steps, prefix=path)
    parts: list[_Frame] = []
    if loop.pause_before_item_when is not None:
        parts.append(_pause_frame(path, BEFORE_ITEM))
    parts.append(body)
    if loop.pause_after_item_when is not None:
        parts.append(_pause_frame(path, AFTER_ITEM))
    chained = _chained(parts)
    group = Group(id=path, label=path, members=tuple(node.id for node in chained.nodes))
    return _Frame(nodes=chained.nodes, edges=chained.edges, groups=(group, *body.groups))


def _pause_frame(path: str, position: str) -> _Frame:
    return _Frame(nodes=(_item_checkpoint(path, position),), edges=())


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
        label=_call_label(call) if call is not None else step.id,
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


def _call_label(call: NodeCall) -> str:
    return f"{call.name}@{'latest' if call.version is None else call.version}"


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
