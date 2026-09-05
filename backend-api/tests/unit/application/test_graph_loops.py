"""`build_template_graph` over the one loop construct: entry, exit, members, and the call.

The three loop rows of the story's matrix differ in one line — which pause key the loop
declares — so the template is written once, in `graph_cases.py`, and each test here supplies
the pause key. The synthetic `{loop}.before` / `{loop}.after` checkpoints and the collapsed
`uses: template` node are both asserted here, because both are things a loop draws that a
flat template never does.
"""

from __future__ import annotations

from orchestrator.application.graph import (
    Group,
    NodeCall,
    build_template_graph,
)
from orchestrator.application.steps import CHECKPOINT_KIND, TEMPLATE_CALL_KIND
from orchestrator.application.templates.validate import validate
from tests.unit.application.graph_cases import (
    PAUSE_AFTER,
    PAUSE_BEFORE,
    edge_pairs,
    graph_of,
    loop,
    node,
    node_ids,
    templates,
    validated,
)
from tests.unit.fakes.templates import FakeTemplateVersionRepository

__all__ = ["templates"]

# --- the loop: entry, exit, group members, and the collapsed call ---------------------------


def test_a_loop_with_no_pause_key_holds_only_its_inner_steps(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(loop(), templates)

    assert node_ids(graph) == ("first", "items.call", "last")
    assert graph.groups == (Group(id="items", label="items", members=("items.call",)),)
    assert edge_pairs(graph) == (("first", "items.call"), ("items.call", "last"))


def test_a_group_is_labelled_by_its_loop_id_and_named_for_the_one_construct_it_draws(
    templates: FakeTemplateVersionRepository,
) -> None:
    """`Group{id, label, kind, members}`: 3.6 draws the box, and the box carries a name."""
    group = graph_of(loop(), templates).groups[0]

    assert group.id == "items"
    assert group.label == "items"
    assert group.kind == "for_each"


def test_pause_after_item_when_appends_a_synthetic_checkpoint(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(loop(PAUSE_AFTER), templates)

    assert node_ids(graph) == ("first", "items.call", "items.after", "last")
    assert graph.groups == (
        Group(id="items", label="items", members=("items.call", "items.after")),
    )


def test_pause_after_item_when_moves_the_outgoing_edge_off_the_checkpoint(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(loop(PAUSE_AFTER), templates)

    assert edge_pairs(graph) == (
        ("first", "items.call"),
        ("items.call", "items.after"),
        ("items.after", "last"),
    )


def test_pause_before_item_when_puts_the_checkpoint_first_in_the_group(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(loop(PAUSE_BEFORE), templates)

    assert node_ids(graph) == ("first", "items.before", "items.call", "last")
    assert graph.groups == (
        Group(id="items", label="items", members=("items.before", "items.call")),
    )


def test_the_previous_steps_edge_enters_the_before_checkpoint_not_the_first_real_step(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(loop(PAUSE_BEFORE), templates)

    assert edge_pairs(graph) == (
        ("first", "items.before"),
        ("items.before", "items.call"),
        ("items.call", "last"),
    )


def test_both_pause_keys_together_wrap_the_inner_steps(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(loop(PAUSE_BEFORE + PAUSE_AFTER), templates)

    assert node_ids(graph) == ("first", "items.before", "items.call", "items.after", "last")
    assert edge_pairs(graph) == (
        ("first", "items.before"),
        ("items.before", "items.call"),
        ("items.call", "items.after"),
        ("items.after", "last"),
    )


def test_a_synthetic_item_checkpoint_is_a_human_checkpoint_of_the_checkpoint_kind(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(loop(PAUSE_BEFORE), templates)
    checkpoint = node(graph, "items.before")

    assert checkpoint.kind == CHECKPOINT_KIND
    assert checkpoint.gate == "human"
    assert checkpoint.human is True
    assert checkpoint.agent is False
    assert checkpoint.call is None


def test_a_synthetic_item_checkpoint_is_labelled_by_where_in_the_item_it_pauses(
    templates: FakeTemplateVersionRepository,
) -> None:
    """The group already carries the loop id; the label says where in the item it pauses."""
    graph = graph_of(loop(PAUSE_AFTER), templates)

    assert node(graph, "items.after").label == "after"


def test_the_connecting_edge_is_ordered_before_the_frames_own_edges(
    templates: FakeTemplateVersionRepository,
) -> None:
    """`baseline->stories.story` reads before `stories.story->stories.after` (Design Notes)."""
    graph = graph_of(loop(PAUSE_AFTER), templates)
    pairs = edge_pairs(graph)

    assert pairs.index(("first", "items.call")) < pairs.index(("items.call", "items.after"))


# --- collapsed calls -------------------------------------------------------------------------


def test_a_uses_template_step_is_exactly_one_node_naming_its_callee(
    templates: FakeTemplateVersionRepository,
) -> None:
    graph = graph_of(loop(), templates)
    call = node(graph, "items.call")

    assert call.kind == TEMPLATE_CALL_KIND
    assert call.call == NodeCall(name="leaf", version=1)
    assert call.label == "leaf@1"


def test_a_collapsed_call_has_no_gate_of_its_own(
    templates: FakeTemplateVersionRepository,
) -> None:
    """The callee's steps carry the gates; `validate()` never reports a call `unvalidated`."""
    result = validated(loop(), templates)
    assert result.template is not None
    graph = build_template_graph(result.template)

    assert node(graph, "items.call").gate is None
    assert result.unvalidated == ()


def test_the_callee_is_never_expanded_into_the_callers_graph(
    templates: FakeTemplateVersionRepository,
) -> None:
    """`leaf@1`'s own `sync` step is invisible here — the guarantee is per file (Epic 4)."""
    graph = graph_of(loop(), templates)

    assert "sync" not in node_ids(graph)
    assert "items.call.sync" not in node_ids(graph)


# --- the synthetic ids are reserved, so a node id stays a unique key -------------------------

#: A loop that declares the `after` pause key *and* an inner step called `after`: both want
#: the path `items.after`, which is one path for two rows.
COLLIDING = """\
name: colliding
version: 1
inputs:
  folder: { type: path, required: true }
steps:
  - id: items
    for_each: "{{folder}}/items.yaml"
    as: item
    pause_after_item_when: "item.done_checkpoint"
    steps:
      - id: after
        uses: git.sync
        gate: deterministic
"""

#: The same file with the pause key removed: nothing plans `items.after` any more, so the
#: step may have the name back.
FREE = COLLIDING.replace('    pause_after_item_when: "item.done_checkpoint"\n', "")


def test_a_step_may_not_take_the_path_a_pause_key_already_plans_a_row_at(
    templates: FakeTemplateVersionRepository,
) -> None:
    """Two rows at `items.after` would make the node id stop being the key `unvalidated`
    joins to — the same offence as two steps sharing an id, reported the same way."""
    result = validate(COLLIDING, templates=templates)

    assert [error.reason for error in result.errors] == ["duplicate step id"]


def test_the_words_are_reserved_only_by_the_pause_key_that_plans_them(
    templates: FakeTemplateVersionRepository,
) -> None:
    """No pause key, no synthetic node, no collision: `after` is a step id like any other."""
    graph = graph_of(FREE, templates)

    assert node_ids(graph) == ("items.after",)
    assert node(graph, "items.after").kind == "git.sync"


def test_a_before_step_collides_only_with_the_before_pause_key(
    templates: FakeTemplateVersionRepository,
) -> None:
    reserved = COLLIDING.replace("id: after", "id: before").replace(
        "pause_after_item_when", "pause_before_item_when"
    )
    free = COLLIDING.replace("id: after", "id: before")

    assert [error.reason for error in validate(reserved, templates=templates).errors] == [
        "duplicate step id"
    ]
    assert validate(free, templates=templates).errors == ()


# --- a call is a path segment, whatever it declares ------------------------------------------

#: The key table accepts `gate` on a `uses: template` step. A file may therefore write one.
GATED_CALL = """\
name: gated
version: 1
inputs:
  folder: { type: path, required: true }
steps:
  - id: items
    for_each: "{{folder}}/items.yaml"
    as: item
    steps:
      - id: call
        uses: template
        gate: human
        with:
          name: leaf
          version: 1
"""


def test_a_call_that_declares_a_gate_still_has_none(
    templates: FakeTemplateVersionRepository,
) -> None:
    """A call is a path segment, not a row (AD-15): there is no gate for it to carry, and
    the published schema says `null` on a call without qualification."""
    graph = graph_of(GATED_CALL, templates)

    assert node(graph, "items.call").gate is None


def test_a_call_that_declares_the_human_gate_is_not_drawn_as_a_human_stop(
    templates: FakeTemplateVersionRepository,
) -> None:
    """Nobody stops at a path segment; the callee's own steps carry its stops."""
    graph = graph_of(GATED_CALL, templates)

    assert node(graph, "items.call").human is False
