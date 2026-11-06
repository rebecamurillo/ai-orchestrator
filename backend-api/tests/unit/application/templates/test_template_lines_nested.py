"""Line bookkeeping for nested loops (story 2, 2026-11-06, AD-15 amendment)."""

from __future__ import annotations

from datetime import date

from orchestrator.application.templates.lines import (
    ITEM_TYPE,
    TEXT_TYPE,
    LinedMap,
    bind_names,
    iter_scoped_steps,
    iter_steps,
    load_with_lines,
)

DEEP = """name: t
steps:
  - id: top
    uses: git.sync
  - id: outer
    for_each: a
    as: epic
    bind: { folder: x }
    steps:
      - id: mid
        uses: git.sync
      - id: inner
        for_each: b
        as: story
        bind: { other: y }
        steps:
          - id: leaf
            uses: git.sync
"""


def root_of(text: str) -> LinedMap:
    loaded = load_with_lines(text)
    assert loaded.root is not None
    return loaded.root


def test_key_order_keeps_non_string_and_repeated_keys_with_their_lines() -> None:
    root = root_of("5: a\n~: b\n2026-01-01: c\nk: d\nk: e\n")

    assert root.key_order == [(5, 1), (None, 2), (date(2026, 1, 1), 3), ("k", 4), ("k", 5)]
    assert root["k"] == "e"


def test_iter_steps_recurses_and_carries_the_innermost_as() -> None:
    found = [(node["id"], item) for node, item in iter_steps(root_of(DEEP))]

    assert found == [
        ("top", None),
        ("outer", None),
        ("mid", "epic"),
        ("inner", "epic"),
        ("leaf", "story"),
    ]


def test_iter_steps_carries_none_when_the_loops_as_is_not_a_string() -> None:
    text = "steps:\n  - id: a\n    for_each: x\n    as: 5\n    steps:\n      - id: b\n"

    assert [(n["id"], i) for n, i in iter_steps(root_of(text))] == [("a", None), ("b", None)]


def test_iter_scoped_steps_gives_each_node_the_names_around_it() -> None:
    found = {node["id"]: scope for node, scope in iter_scoped_steps(root_of(DEEP))}

    assert found["top"] == {}
    assert found["outer"] == {}
    assert found["mid"] == {"epic": ITEM_TYPE, "folder": TEXT_TYPE}
    assert found["inner"] == {"epic": ITEM_TYPE, "folder": TEXT_TYPE}
    assert found["leaf"] == {
        "epic": ITEM_TYPE,
        "folder": TEXT_TYPE,
        "story": ITEM_TYPE,
        "other": TEXT_TYPE,
    }


def test_iter_scoped_steps_skips_bad_bind_keys_and_shapes_without_raising() -> None:
    text = (
        "steps:\n  - id: a\n    for_each: x\n    as: e\n    bind: { 5: x, ok: y, bad-key: z }\n"
        "    steps:\n      - id: b\n  - id: c\n"
    )
    other = (
        "steps:\n  - id: a\n    for_each: x\n    as: 7\n    bind: [1]\n    steps:\n      - id: b\n"
    )

    scoped = {node["id"]: scope for node, scope in iter_scoped_steps(root_of(text))}
    odd = {node["id"]: scope for node, scope in iter_scoped_steps(root_of(other))}

    assert scoped["b"] == {"e": ITEM_TYPE, "ok": TEXT_TYPE}
    assert odd["b"] == {}


def test_bind_names_lists_only_valid_string_keys() -> None:
    node = root_of("bind: { a: 1, 5: 2, B: 3, c_d: 4 }\n")

    assert bind_names(node) == ["a", "c_d"]
    assert bind_names(root_of("bind: oops\n")) == []
