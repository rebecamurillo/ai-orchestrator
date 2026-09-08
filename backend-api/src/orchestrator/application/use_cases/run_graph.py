"""`run_graph_for` — `GET /runs/{id}/graph`'s one read (SPEC CAP-12, AD-15).

Split out of `run_views.py` on line count alone (`backend-api/AGENTS.md`'s 400-line module
limit), the same reason `run_view_types.py`'s own module doc gives for its own split — that
one's `run_views.py`/`graph.py`/`graph_schema.py` precedent, applied here now that 5.10's
`Alert.attribution` and `LatestAttempt.cost_provisional` need the room. `run_views.py`
imports this back and keeps `run_graph_for` in its own `__all__`, so `api/routers/graph.py`
and `tests/unit/application/test_run_views.py` (both of which import it from `run_views`)
keep resolving unchanged.
"""

from __future__ import annotations

from uuid import UUID

from orchestrator.application.graph import Graph, build_run_graph
from orchestrator.application.use_cases.run_view_types import RunViewPorts
from orchestrator.domain.errors import NotFound

__all__ = ["run_graph_for"]


def run_graph_for(ports: RunViewPorts, run_id: UUID) -> Graph:
    """The one read `GET /runs/{id}/graph` needs: the Run and its rows, then `build_run_graph`
    (`application/graph.py`). Raising `NotFound` here, not in the router, matches `run_detail`
    (`run_views.py`) and `create_run.py::get_run` — the router stays a thin parse-call-map,
    per `backend-api/AGENTS.md`'s "Routers are thin" rule."""
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run {run_id}")
    rows = ports.steps.list_for_run(run_id)
    return build_run_graph(rows, run)
