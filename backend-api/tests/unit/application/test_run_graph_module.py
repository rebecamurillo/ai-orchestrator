"""`application/run_graph.py` is the run-graph half of `graph.py`; `graph` re-exports it."""

from orchestrator.application import graph, run_graph


def test_graph_reexports_the_run_graph_names() -> None:
    assert graph.build_run_graph is run_graph.build_run_graph
    assert graph.group_status is run_graph.group_status
    assert graph.ROOT_ID == run_graph.ROOT_ID
    assert graph.STEP_TOKENS is run_graph.STEP_TOKENS
