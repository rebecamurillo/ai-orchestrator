"""The Template texts and helpers the graph test modules share (3.4).

One home rather than two copies: `test_graph.py` and `test_graph_loops.py` assert different
properties of the same handful of files, and a second copy of the loop template is a second
thing to keep in step with the validator. Every helper here builds a graph the way the
endpoint does — text through `validate()`, the tree through `build_template_graph` — because
the property that matters most is a *join*, and a hand-built `ParsedTemplate` could satisfy
the graph while disagreeing with the validator.
"""

from __future__ import annotations

import pytest

from orchestrator.application.graph import (
    Graph,
    Node,
    build_template_graph,
)
from orchestrator.application.templates.model import ValidationResult
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateVersion
from tests.unit.fakes.templates import FakeTemplateVersionRepository

LEAF = "name: leaf\nversion: 1\nsteps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"

#: A loop whose body is one collapsed call. The three loop rows of the matrix differ in one
#: line — which pause key the loop declares — so the rest is written once, here.
LOOP_HEAD = """\
name: outer
version: 1
inputs:
  folder: { type: path, required: true }
steps:
  - id: first
    uses: git.sync
    gate: deterministic
  - id: items
    for_each: "{{folder}}/items.yaml"
    as: item
"""

LOOP_TAIL = """\
    steps:
      - id: call
        uses: template
        with:
          name: leaf
          version: 1
  - id: last
    uses: git.push
    with: { branch: "main" }
    gate: deterministic
"""

PAUSE_BEFORE = '    pause_before_item_when: "item.spec_checkpoint"\n'
PAUSE_AFTER = '    pause_after_item_when: "item.done_checkpoint"\n'


def loop(pause: str = "") -> str:
    """The loop template, with whichever pause key the scenario declares (or none)."""
    return LOOP_HEAD + pause + LOOP_TAIL


FLAT = """\
name: flat
version: 1
steps:
  - id: one
    uses: git.sync
    gate: deterministic
  - id: two
    uses: agent
    with: { skill: bmad-build-auto }
    prompts:
      dispatch: "Run the skill {skill}."
      rendered: "Read {path} first."
    gate: liveness
  - id: three
    run: "make test"
    gate: deterministic
"""

#: Two executable steps that declare no gate — one at the root, one inside the loop — plus
#: the explicit `checkpoint` kind and a `human`-gated step that is not a checkpoint.
GATELESS = """\
name: gateless
version: 1
inputs:
  folder: { type: path, required: true }
steps:
  - id: bare
    uses: git.sync
  - id: pause
    uses: checkpoint
  - id: ask
    run: "scripts/ask.sh"
    gate: human
  - id: items
    for_each: "{{folder}}/items.yaml"
    as: item
    steps:
      - id: inner
        uses: git.sync
"""


@pytest.fixture
def templates() -> FakeTemplateVersionRepository:
    """The one callee every collapsed call in this module names."""
    return FakeTemplateVersionRepository(
        [TemplateVersion(name="leaf", version=1, yaml=LEAF, hash="sha")]
    )


def validated(text: str, templates: FakeTemplateVersionRepository) -> ValidationResult:
    result = validate(text, templates=templates)
    assert result.errors == (), result.errors
    return result


def graph_of(text: str, templates: FakeTemplateVersionRepository) -> Graph:
    result = validated(text, templates)
    assert result.template is not None
    return build_template_graph(result.template)


def node_ids(graph: Graph) -> tuple[str, ...]:
    return tuple(found.id for found in graph.nodes)


def edge_pairs(graph: Graph) -> tuple[tuple[str, str], ...]:
    return tuple((edge.from_id, edge.to_id) for edge in graph.edges)


def node(graph: Graph, node_id: str) -> Node:
    return {found.id: found for found in graph.nodes}[node_id]
