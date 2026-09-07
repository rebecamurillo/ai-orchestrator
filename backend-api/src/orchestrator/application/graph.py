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
from orchestrator.application.rules.frames import epic_frame, rows_in_frame, story_frame
from orchestrator.application.steps import (
    AGENT_KIND,
    CHECKPOINT_KIND,
    KIND_META,
    TEMPLATE_CALL_KIND,
)
from orchestrator.application.templates.model import ForEach, ParsedTemplate, Step
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import StepStatus

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


# ── the run graph (4.12, SPEC CAP-12, AD-15) ──────────────────────────────────────────────
#
# Where the template graph collapses a call and never expands a loop, the run graph is the
# opposite: the planner (4.2) has already expanded every loop into concrete rows, so there
# is nothing left to collapse and nothing left to expand here. A node is one `StepRun`, its
# id is `step_run.path` verbatim, and the only structure this module adds on top is the one
# the walker itself has: a straight chain in `seq` order, with one synthetic node standing
# for the Run as a whole at the head of it, and the `epics[i]`/`epics[i].stories[j]` frames
# `application/rules/frames.py` already knows how to find, read as `Group`s.

#: The synthetic node id that stands for the Run itself — never a `step_run.path`, since
#: every shipped Template's step ids are plain identifiers with no brackets in them at the
#: top level, so this can never collide with a real row.
ROOT_ID = "root"

#: Step tokens (Consistency Conventions — Status tokens), for a run graph's per-row nodes.
STEP_TOKENS: dict[StepStatus, str] = {
    "planned": "QUE",
    "queued": "QUE",
    "running": "RUN",
    "done": "DON",
    "blocked": "BLK",
    "checkpoint": "CHK",
    "error": "ERR",
    "skipped": "SKP",
}

#: The three statuses that mean the whole Run — and so every group containing the row — is
#: stopped for the Operator. Checked before `running`: the walker parks the Run the moment
#: any one row reaches one of these, so at most one row in the whole plan can be in this set
#: at a time, and nothing else can be `running` alongside it — the precedence below is a
#: total order for a case that is unreachable in practice, not a live ambiguity.
_STOPPED: tuple[StepStatus, ...] = ("error", "blocked", "checkpoint")


def group_status(statuses: Sequence[StepStatus]) -> str:
    """The one rule (SPEC CAP-12, AD-15) a run-graph group's status follows, and the only
    place it is written: `error | blocked | checkpoint` if any member is, else `running` if
    any is, else `skipped` when every member is, else `done` when every member is `done` or
    `skipped`, else `queued`. `queued` for an empty sequence too — a group is only ever built
    from a prefix some row actually named (`_group_prefixes`), so this is never reached
    empty in practice, but `all(...)` over `[]` is vacuously true and would otherwise answer
    the wrong branch (`skipped`) for a case that never means that."""
    if not statuses:
        return "queued"
    for stopped in _STOPPED:
        if stopped in statuses:
            return stopped
    if "running" in statuses:
        return "running"
    if all(status == "skipped" for status in statuses):
        return "skipped"
    if all(status in ("done", "skipped") for status in statuses):
        return "done"
    return "queued"


def _run_token(run: Run) -> str:
    """The Run's own UI token (Consistency Conventions — Status tokens): `BLK`/`CHK` while
    parked, off `park_kind`, the fixed table otherwise. The same rule `application/use_cases/
    project_runs.py::_token` states for the Board — duplicated rather than imported, that
    module's own established precedent for a handful of lines two readers both need."""
    if run.status == "needs_you":
        return "CHK" if run.park_kind == "checkpoint" else "BLK"
    return {
        "queued": "QUE",
        "running": "RUN",
        "done": "DON",
        "failed": "ERR",
        "cancelled": "CAN",
    }[run.status]


def _run_node(run: Run) -> Node:
    """The one synthetic node standing for the Run: `initiative` → the initiative, else the
    epic (`run.template_name` names whichever it is) — the graph's own root."""
    return Node(
        id=ROOT_ID,
        kind=run.template_name,
        label=run.template_name,
        gate=None,
        status=run.status,
        token=_run_token(run),
        current=False,
    )


def _row_node(row: StepRun, *, current: bool) -> Node:
    """One planned row, as one box: `step_run.path` verbatim, no index ever stripped."""
    return Node(
        id=row.path,
        kind=row.kind,
        label=row.label,
        gate=row.gate,
        agent=row.kind == AGENT_KIND,
        human=row.gate == HUMAN_GATE or row.kind == CHECKPOINT_KIND,
        status=row.status,
        token=STEP_TOKENS[row.status],
        current=current,
    )


def _is_current(row: StepRun, run: Run) -> bool:
    """The running row, or the parked row while nothing is running (SPEC CAP-12)."""
    return row.status == "running" or (run.park_path is not None and row.path == run.park_path)


def _group_prefixes(rows: Sequence[StepRun]) -> list[str]:
    """Every distinct `epics[i]` and `epics[i].stories[j]` (or `stories[j]`) frame present,
    in the plan's own order — the first row of a frame is where it starts."""
    seen: dict[str, int] = {}
    for row in rows:
        for prefix in (epic_frame(row.path), story_frame(row.path)):
            if prefix is not None and prefix not in seen:
                seen[prefix] = row.seq
    return sorted(seen, key=lambda prefix: seen[prefix])


def _group(prefix: str, rows: Sequence[StepRun], *, cancelled: bool) -> Group:
    """One frame, its members in `seq` order, and its status by the one rule — `None` for a
    `cancelled` Run, which never finished or stopped at any of them (SPEC CAP-12)."""
    members = rows_in_frame(rows, prefix)
    status = None if cancelled else group_status([member.status for member in members])
    return Group(
        id=prefix,
        label=prefix,
        members=tuple(member.path for member in members),
        status=status,
    )


def build_run_graph(rows: Sequence[StepRun], run: Run) -> Graph:
    """The graph of one Run: its planned rows, chained in `seq` order behind one root node
    standing for the Run itself, grouped by the epic/story frames they fall under."""
    ordered = sorted(rows, key=lambda row: row.seq)
    root = _run_node(run)
    row_nodes = [_row_node(row, current=_is_current(row, run)) for row in ordered]
    nodes = (root, *row_nodes)
    edges = _chain((ROOT_ID, *(row.path for row in ordered)))
    groups = tuple(
        _group(prefix, ordered, cancelled=run.status == "cancelled")
        for prefix in _group_prefixes(ordered)
    )
    return Graph(nodes=nodes, edges=edges, groups=groups)
