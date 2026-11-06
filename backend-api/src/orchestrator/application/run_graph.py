"""The graph of one Run: its planned rows, chained in `seq` order behind a root node (AD-15).

Split from `graph.py` for the module size limit; `graph` re-exports every name here.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

from orchestrator.application.graph_schema import (
    HUMAN_GATE,
    Edge,
    Graph,
    Group,
    Node,
)
from orchestrator.application.rules.frames import epic_frame, rows_in_frame, story_frame
from orchestrator.application.steps import AGENT_KIND, CHECKPOINT_KIND
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import CHK_PARK_KINDS, StepStatus


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
        return "CHK" if run.park_kind in CHK_PARK_KINDS else "BLK"
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
    `cancelled` Run, which never finished or stopped at any of them (SPEC CAP-12).

    k/n semantics (story 1-5): k = count of `done` members; n = count of members with
    status != 'skipped'. Both are computed from member statuses even for cancelled runs.
    """
    members = rows_in_frame(rows, prefix)
    status = None if cancelled else group_status([member.status for member in members])
    k = sum(1 for m in members if m.status == "done")
    n = sum(1 for m in members if m.status != "skipped")
    return Group(
        id=prefix,
        label=prefix,
        members=tuple(member.path for member in members),
        status=status,
        k=k,
        n=n,
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
