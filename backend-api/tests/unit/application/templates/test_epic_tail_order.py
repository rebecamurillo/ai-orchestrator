"""Epic tail order: a human gate must be reachable from the `push` step.

Tests the behavioral invariant that `templates/epic.yaml` parks the operator
*after* the branch has been pushed — not before. The BFS starts from the
step id "push"; if that step is renamed the test must be updated accordingly.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from orchestrator.application.graph import build_template_graph
from orchestrator.application.templates.validate import validate
from orchestrator.application.use_cases.templates import TemplatePorts, seed_shipped
from orchestrator.infrastructure.templates_loader import load_shipped_templates
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.templates import FakeTemplateVersionRepository

#: `tests/unit/application/templates/test_epic_tail_order.py` -> the repository root.
SHIPPED_DIR = Path(__file__).resolve().parents[5] / "templates"

AT = datetime(2026, 9, 10, tzinfo=UTC)


def seeded() -> FakeTemplateVersionRepository:
    """Every shipped file, through the exact seeding `main.py` runs at start-up."""
    templates = FakeTemplateVersionRepository()
    uow = FakeUnitOfWork()
    uow.__enter__()
    ports = TemplatePorts(uow=uow, templates=templates, clock=FakeClock(AT))
    seed_shipped(ports, load_shipped_templates(SHIPPED_DIR))
    return templates


def test_epic_has_a_human_gate_reachable_from_push() -> None:
    """After push, at least one human-gate node must be reachable in the epic graph.

    This invariant guarantees the operator parks with a real pushed branch
    available for review, not before the push runs. The BFS starts from the
    step with id "push" — if that step is renamed, this test must be updated.
    """
    templates = seeded()

    latest_version = max(templates.list_versions("epic"))
    stored = templates.versions[("epic", latest_version)]
    result = validate(stored.yaml, templates=templates)
    assert result.template is not None, result.errors

    graph = build_template_graph(result.template)

    node_ids = {node.id for node in graph.nodes}
    assert "push" in node_ids, (
        f"expected a 'push' step in the epic graph; found: {node_ids!r}"
    )

    # Collect all human-gate node ids.
    human_ids = {node.id for node in graph.nodes if node.human}
    assert human_ids, "expected at least one human-gate node in the epic graph"

    # Build a forward adjacency list from graph edges.
    adjacency: dict[str, list[str]] = {}
    for edge in graph.edges:
        adjacency.setdefault(edge.from_id, []).append(edge.to_id)

    # BFS from the 'push' node to find all reachable descendants.
    visited: set[str] = set()
    queue: deque[str] = deque(["push"])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        queue.extend(adjacency.get(current, []))

    reachable_human = visited & human_ids
    assert reachable_human, (
        f"expected a human-gate node reachable from 'push'; "
        f"human nodes in epic graph: {human_ids!r}, "
        f"nodes reachable from 'push': {visited!r}"
    )
