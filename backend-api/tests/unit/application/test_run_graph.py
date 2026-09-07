"""`build_run_graph` and `group_status` — the run graph's nodes, tokens, and groups (4.12,
SPEC CAP-12, AD-15).

The run graph is the expanded rows a Run actually planned, not the template it was planned
from: node ids are `step_run.path` verbatim (indices and all), edges are the plan's own
`seq` order, and groups are the `epics[i]`/`epics[i].stories[j]` frames `application/rules/
frames.py` already knows how to find. `group_status` is asserted on its own, once, for
every branch of the one rule — nothing else in this module restates it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.application.graph import build_run_graph, group_status
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.statuses import StepStatus

NOW = datetime(2026, 1, 1, tzinfo=UTC)
RUN_ID = UUID("01960000-0000-7000-9000-0000000000aa")


def run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": RUN_ID,
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("10"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def row(path: str, *, status: StepStatus = "planned", seq: int, kind: str = "shell") -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=RUN_ID,
        seq=seq,
        path=path,
        label=path.rsplit(".", maxsplit=1)[-1],
        kind=kind,
        gate="deterministic",
        status=status,
    )


# ── node ids, tokens, current ────────────────────────────────────────────────────────────


def test_node_ids_are_step_run_paths_verbatim() -> None:
    rows = [
        row("checkout", seq=1, status="done"),
        row("stories[0].commit-guard", seq=2, status="running"),
    ]
    graph = build_run_graph(rows, run())

    ids = {node.id for node in graph.nodes}
    assert "checkout" in ids
    assert "stories[0].commit-guard" in ids


def test_every_step_status_maps_to_its_fixed_token() -> None:
    table: dict[StepStatus, str] = {
        "planned": "QUE",
        "queued": "QUE",
        "running": "RUN",
        "done": "DON",
        "blocked": "BLK",
        "checkpoint": "CHK",
        "error": "ERR",
        "skipped": "SKP",
    }
    rows = [row(status, seq=i, status=status) for i, status in enumerate(table, start=1)]
    graph = build_run_graph(rows, run())

    by_id = {node.id: node for node in graph.nodes}
    for status, token in table.items():
        assert by_id[status].token == token, status
        assert by_id[status].status == status


def test_current_marks_the_running_row() -> None:
    rows = [row("a", seq=1, status="done"), row("b", seq=2, status="running")]
    graph = build_run_graph(rows, run())

    by_id = {node.id: node for node in graph.nodes}
    assert by_id["a"].current is False
    assert by_id["b"].current is True


def test_current_marks_the_park_row_when_nothing_is_running() -> None:
    rows = [row("a", seq=1, status="done"), row("b", seq=2, status="blocked")]
    parked = run(status="needs_you", park_kind="blocked", park_path="b")
    graph = build_run_graph(rows, parked)

    by_id = {node.id: node for node in graph.nodes}
    assert by_id["b"].current is True
    assert by_id["a"].current is False


def test_edges_chain_the_root_through_every_row_in_seq_order() -> None:
    rows = [row("a", seq=1), row("b", seq=2), row("c", seq=3)]
    graph = build_run_graph(rows, run())

    pairs = [(edge.from_id, edge.to_id) for edge in graph.edges]
    assert pairs == [("root", "a"), ("a", "b"), ("b", "c")]


# ── root node / root token ───────────────────────────────────────────────────────────────


def test_the_root_node_carries_the_run_token() -> None:
    rows = [row("a", seq=1, status="running")]
    graph = build_run_graph(rows, run(status="running"))

    root = next(node for node in graph.nodes if node.id == "root")
    assert root.token == "RUN"


def test_a_cancelled_run_roots_at_can() -> None:
    rows = [row("a", seq=1, status="error")]
    graph = build_run_graph(rows, run(status="cancelled"))

    root = next(node for node in graph.nodes if node.id == "root")
    assert root.token == "CAN"


def test_a_parked_run_roots_at_chk_or_blk_by_park_kind() -> None:
    rows = [row("a", seq=1, status="checkpoint")]
    graph = build_run_graph(rows, run(status="needs_you", park_kind="checkpoint", park_path="a"))

    root = next(node for node in graph.nodes if node.id == "root")
    assert root.token == "CHK"


# ── groups: epic and story frames ────────────────────────────────────────────────────────


def _initiative_rows() -> list[StepRun]:
    return [
        row("epics[0].checkout", seq=1, status="done"),
        row("epics[0].stories[0].sync", seq=2, status="done"),
        row(
            "epics[0].stories[0].commit-guard",
            seq=3,
            status="done",
            kind="git.commit",
        ),
        row("epics[0].stories[1].sync", seq=4, status="running"),
        row("epics[0].push", seq=5, status="planned", kind="git.push"),
        row("epics[1].checkout", seq=6, status="planned"),
    ]


def test_groups_cover_every_epic_and_story_frame() -> None:
    graph = build_run_graph(_initiative_rows(), run(template_name="initiative"))

    ids = {group.id for group in graph.groups}
    assert ids == {
        "epics[0]",
        "epics[0].stories[0]",
        "epics[0].stories[1]",
        "epics[1]",
    }


def test_a_group_members_are_every_row_nested_under_it() -> None:
    graph = build_run_graph(_initiative_rows(), run(template_name="initiative"))

    epic0 = next(group for group in graph.groups if group.id == "epics[0]")
    assert epic0.members == (
        "epics[0].checkout",
        "epics[0].stories[0].sync",
        "epics[0].stories[0].commit-guard",
        "epics[0].stories[1].sync",
        "epics[0].push",
    )


def test_a_cancelled_run_has_no_group_statuses() -> None:
    graph = build_run_graph(_initiative_rows(), run(template_name="initiative", status="cancelled"))

    assert all(group.status is None for group in graph.groups)


def test_a_non_cancelled_run_groups_carry_a_status() -> None:
    graph = build_run_graph(_initiative_rows(), run(template_name="initiative"))

    epic1 = next(group for group in graph.groups if group.id == "epics[1]")
    assert epic1.status == "queued"


# ── the one rule: group_status, every branch ─────────────────────────────────────────────


def test_group_status_is_error_when_any_member_errored() -> None:
    assert group_status(["done", "error", "queued"]) == "error"


def test_group_status_is_blocked_when_any_member_is_blocked() -> None:
    assert group_status(["done", "blocked"]) == "blocked"


def test_group_status_is_checkpoint_when_any_member_is_checkpoint() -> None:
    assert group_status(["done", "checkpoint"]) == "checkpoint"


def test_group_status_is_running_when_any_member_runs_and_none_is_stopped() -> None:
    assert group_status(["done", "running", "queued"]) == "running"


def test_group_status_is_skipped_when_every_member_is_skipped() -> None:
    assert group_status(["skipped", "skipped"]) == "skipped"


def test_group_status_is_done_when_every_member_is_done_or_skipped() -> None:
    assert group_status(["done", "skipped", "done"]) == "done"


def test_group_status_is_queued_otherwise() -> None:
    assert group_status(["planned", "queued"]) == "queued"


def test_group_status_precedence_favours_a_stop_over_running() -> None:
    """Unreachable in practice — the walker parks the whole Run on the first stop, so no
    other row can be `running` at the same time — but the function is still total."""
    assert group_status(["running", "blocked"]) == "blocked"


def test_group_status_is_queued_for_an_empty_sequence() -> None:
    """Unreachable via `build_run_graph` (a group is only ever built from a prefix some row
    named), kept as a total function rather than one that trusts its caller — `all(...)`
    over `[]` is vacuously true and would otherwise wrongly answer `skipped`."""
    assert group_status([]) == "queued"
