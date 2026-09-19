"""The four exemplar Templates, as graphs (3.4 acceptance criteria).

`test_graph.py` proves the rules against templates written for the rule they exercise. This
module proves the *result* against full-sized realistic files, asserted as exact ordered
tuples — the ordering is the whole point of a graph the diagram draws left to right, and a
set comparison would pass on a reversed chain.

The files are the frozen copies under `templates/fixtures/exemplars/` — a snapshot of the
shipped Templates taken when the suite was decoupled from `templates/*.yaml`, so the
shipped files evolve freely without breaking the graph coverage here (the shipped files
themselves are covered by `templates/test_shipped_smoke.py`). Each file's text sits in a
fake repository holding all four with `calls` pinned exactly as saving them would pin them.
Read here rather than imported from `test_shipped_templates.py`, which is an anchor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.application.graph import Edge, Graph, Group, Node, NodeCall, build_template_graph
from orchestrator.application.steps import CHECKPOINT_KIND, TEMPLATE_CALL_KIND
from orchestrator.application.templates.model import ForEach
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from tests.unit.fakes.templates import FakeTemplateVersionRepository

#: The frozen exemplar Templates — never the shipped `templates/*.yaml`.
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "fixtures" / "exemplars"

NAMES = ("repo-init", "story", "epic", "initiative")

TEXTS: dict[str, str] = {name: (TEMPLATES_DIR / f"{name}.yaml").read_text() for name in NAMES}

#: `repo-init@1`'s five steps, in file order.
REPO_INIT_NODES = ("checkout", "install", "context", "context-review", "commit", "push", "link")
REPO_INIT_STEPS = 7


@pytest.fixture
def templates() -> FakeTemplateVersionRepository:
    """All four shipped versions, `calls` pinned exactly as saving each one would record."""
    return FakeTemplateVersionRepository(
        [
            TemplateVersion(name="repo-init", version=1, yaml=TEXTS["repo-init"], hash="sha"),
            TemplateVersion(name="story", version=1, yaml=TEXTS["story"], hash="sha"),
            TemplateVersion(
                name="epic",
                version=1,
                yaml=TEXTS["epic"],
                hash="sha",
                calls=(TemplateRef(name="story", version=1),),
            ),
            TemplateVersion(
                name="initiative",
                version=1,
                yaml=TEXTS["initiative"],
                hash="sha",
                calls=(TemplateRef(name="epic", version=1),),
            ),
        ]
    )


def graph_of(name: str, templates: FakeTemplateVersionRepository) -> Graph:
    result = validate(TEXTS[name], templates=templates)
    assert result.errors == (), result.errors
    assert result.template is not None
    return build_template_graph(result.template)


def node_ids(graph: Graph) -> tuple[str, ...]:
    return tuple(node.id for node in graph.nodes)


def edge_pairs(graph: Graph) -> tuple[tuple[str, str], ...]:
    return tuple((edge.from_id, edge.to_id) for edge in graph.edges)


def node(graph: Graph, node_id: str) -> Node:
    return {found.id: found for found in graph.nodes}[node_id]


# --- repo-init@1: seven steps, one chain, no group, no call --------------------------------


def test_repo_init_is_seven_nodes_in_file_order(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of("repo-init", templates)

    assert node_ids(graph) == REPO_INIT_NODES
    assert len(graph.nodes) == REPO_INIT_STEPS


def test_repo_init_chains_its_seven_steps_and_declares_no_group(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of("repo-init", templates)

    assert edge_pairs(graph) == (
        ("checkout", "install"),
        ("install", "context"),
        ("context", "context-review"),
        ("context-review", "commit"),
        ("commit", "push"),
        ("push", "link"),
    )
    assert graph.groups == ()


def test_the_repo_init_stop_is_the_one_node_a_person_decides(
    templates: FakeTemplateVersionRepository,
) -> None:
    """`application/graph.py::_is_human`: the `checkpoint` kind, and the `human` gate."""
    graph = graph_of("repo-init", templates)

    assert [found.id for found in graph.nodes if found.human] == ["context-review"]


def test_no_repo_init_node_carries_a_call(templates: FakeTemplateVersionRepository) -> None:
    graph = graph_of("repo-init", templates)

    assert all(found.call is None for found in graph.nodes)


# --- story@1: the agent step and its gates -------------------------------------------------


def test_story_is_four_nodes_chained_sync_build_verify_commit_guard(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of("story", templates)

    assert node_ids(graph) == ("sync", "build", "verify", "commit-guard")
    assert edge_pairs(graph) == (
        ("sync", "build"),
        ("build", "verify"),
        ("verify", "commit-guard"),
    )
    assert graph.groups == ()


def test_story_build_is_the_one_agent_step_and_is_gated_on_liveness(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of("story", templates)

    assert [found.id for found in graph.nodes if found.agent] == ["build"]
    assert node(graph, "build").gate == "liveness"


def test_story_verify_and_commit_guard_are_deterministic(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of("story", templates)

    assert node(graph, "verify").gate == "deterministic"
    assert node(graph, "commit-guard").gate == "deterministic"


def test_story_has_no_human_node_and_no_group(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of("story", templates)

    assert [found.id for found in graph.nodes if found.human] == []
    assert graph.groups == ()


# --- epic@1: the golden shape --------------------------------------------------------------


def test_epic_is_the_golden_shape(templates: FakeTemplateVersionRepository) -> None:
    """Design Notes, "Golden shape": the nodes, the group and the edges, in that order.

    Updated 2026-09-17 (story 4-4): spec-gate agent step inserted after baseline.
    """
    graph = graph_of("epic", templates)

    assert node_ids(graph) == (
        "checkout",
        "setup",
        "baseline",
        "spec-gate",
        "stories.story",
        "stories.after",
        "e2e",
        "push",
        "link",
    )
    assert graph.groups == (
        Group(id="stories", label="stories", members=("stories.story", "stories.after")),
    )
    assert edge_pairs(graph) == (
        ("checkout", "setup"),
        ("setup", "baseline"),
        ("baseline", "spec-gate"),
        ("spec-gate", "stories.story"),
        ("stories.story", "stories.after"),
        ("stories.after", "e2e"),
        ("e2e", "push"),
        ("push", "link"),
    )


def test_the_epics_slow_gate_runs_once_and_before_the_push(
    templates: FakeTemplateVersionRepository,
) -> None:
    """The tiering, as a graph claim rather than as a row list.

    `e2e` is the 24-minute gate: once per epic rather than once per Story, and *before*
    `push`, because a branch is not handed over carrying a red integration suite. Both
    halves are read off the chain, so moving the row past `push` fails here.
    """
    ids = node_ids(graph_of("epic", templates))

    assert ids.count("e2e") == 1
    assert ids.index("e2e") < ids.index("push")
    assert ("e2e", "push") in edge_pairs(graph_of("epic", templates))


def test_the_epic_installs_its_toolchain_before_anything_reads_it(
    templates: FakeTemplateVersionRepository,
) -> None:
    """A fresh worktree has no virtualenv: `setup` precedes the first row that needs one."""
    ids = node_ids(graph_of("epic", templates))

    assert ids.index("setup") < ids.index("baseline") < ids.index("stories.story")


def test_epic_collapses_its_call_to_story_into_one_node(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of("epic", templates)
    call = node(graph, "stories.story")

    assert call.kind == TEMPLATE_CALL_KIND
    assert call.call == NodeCall(name="story", version=1)
    assert call.label == "story@1"
    assert call.gate is None


def test_epic_does_not_surface_the_callees_steps(
    templates: FakeTemplateVersionRepository,
) -> None:
    """The known limitation, recorded: `story@1`'s `build` is invisible here (Epic 4)."""
    graph = graph_of("epic", templates)

    assert "build" not in node_ids(graph)


def test_epics_item_checkpoint_is_the_only_human_node(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of("epic", templates)
    after = node(graph, "stories.after")

    assert [found.id for found in graph.nodes if found.human] == ["stories.after"]
    assert after.kind == CHECKPOINT_KIND
    assert after.gate == "human"


# --- initiative@1: a loop and nothing else -------------------------------------------------


def test_initiative_is_one_loop_holding_a_call_and_an_item_checkpoint(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of("initiative", templates)

    assert node_ids(graph) == ("epics.epic", "epics.after")
    assert graph.groups == (
        Group(id="epics", label="epics", members=("epics.epic", "epics.after")),
    )
    assert graph.edges == (Edge(from_id="epics.epic", to_id="epics.after"),)


def test_initiatives_item_checkpoint_is_the_epics_done_checkpoint(
    templates: FakeTemplateVersionRepository,
) -> None:
    """The node exists because the file declares this expression; the expression is what
    Epic 4 evaluates per item, so it is pinned here and not only its graph consequence."""
    result = validate(TEXTS["initiative"], templates=templates)

    assert result.template is not None
    loop = result.template.steps[0]
    assert isinstance(loop, ForEach)
    assert loop.pause_after_item_when == "epic.done_checkpoint"


def test_initiative_collapses_its_call_to_epic(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of("initiative", templates)
    call = node(graph, "epics.epic")

    assert call.kind == TEMPLATE_CALL_KIND
    assert call.call == NodeCall(name="epic", version=1)
    assert call.label == "epic@1"
    assert call.gate is None


# --- the id rule, over every shipped file --------------------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_no_shipped_id_carries_an_index(
    name: str, templates: FakeTemplateVersionRepository
) -> None:
    graph = graph_of(name, templates)
    ids = [*node_ids(graph), *(group.id for group in graph.groups)]

    for found in ids:
        assert "[" not in found and "]" not in found, found
        assert not any(segment.isdigit() for segment in found.split(".")), found


@pytest.mark.parametrize("name", NAMES)
def test_no_shipped_node_reads_unvalidated(
    name: str, templates: FakeTemplateVersionRepository
) -> None:
    """Every shipped step declares a gate, so no shipped graph carries the word."""
    graph = graph_of(name, templates)

    assert all(found.gate != "unvalidated" for found in graph.nodes)


@pytest.mark.parametrize("name", NAMES)
def test_every_edge_names_two_nodes_of_the_same_graph(
    name: str, templates: FakeTemplateVersionRepository
) -> None:
    graph = graph_of(name, templates)
    ids = set(node_ids(graph))

    for edge in graph.edges:
        assert edge.from_id in ids, edge
        assert edge.to_id in ids, edge


@pytest.mark.parametrize("name", NAMES)
def test_every_group_member_is_a_node_of_the_same_graph(
    name: str, templates: FakeTemplateVersionRepository
) -> None:
    graph = graph_of(name, templates)
    ids = set(node_ids(graph))

    for group in graph.groups:
        assert set(group.members) <= ids, group
