"""A `for_each` loop's graph over text this suite owns, against the running stack (3.4).

Added 2026-09-30 (Operator decision: the mono-repo `initiative` and `story-run` workflows are
retired to `templates/drafts/`, no longer seeded). `test_template_graph.py` used to read the
shipped `initiative@1` for the two claims below — a loop group whose `pause_after_item_when`
adds an `.after` item checkpoint, and a call collapsed to one node labelled `name@version`.
The same claims hold here over a caller and a leaf of this suite's own, so no shipped file is
pinned (hard rule 6), and they are proven through the real stack: the leaf is stored through
the real repository, and the caller's graph is built by `POST /templates/{name}/graph`
against that stored callee.

The `POST .../graph` stores nothing; the leaf is a name of its own, made unique per run.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

HTTP_OK = 200
HTTP_CREATED = 201

TEMPLATES = "/api/v1/templates"

LEAF = (
    "name: {name}\nversion: 1\nsteps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
)

#: One loop, one collapsed call, one item checkpoint declared by `pause_after_item_when`.
CALLER = (
    "name: {name}\n"
    "version: 1\n"
    "inputs:\n"
    "  list_folder: {{ type: path, required: true }}\n"
    "steps:\n"
    "  - id: entries\n"
    '    for_each: "{{{{list_folder}}}}/entries.yaml"\n'
    "    as: entry\n"
    '    pause_after_item_when: "entry.done_checkpoint"\n'
    "    steps:\n"
    "      - id: call\n"
    "        uses: template\n"
    "        with:\n"
    "          name: {leaf}\n"
    "          version: 1\n"
)


@pytest.fixture
def leaf_name(authenticated: httpx.Client) -> str:
    """A stored leaf under a name no earlier run of this suite can have taken."""
    name = f"e2e-loop-leaf-{uuid4().hex}"
    created = authenticated.post(
        f"{TEMPLATES}/{name}/versions", json={"yaml": LEAF.format(name=name)}
    )
    assert created.status_code == HTTP_CREATED, created.text
    return name


@pytest.fixture
def caller_graph(authenticated: httpx.Client, leaf_name: str) -> dict[str, object]:
    caller = f"e2e-loop-caller-{uuid4().hex}"
    text = CALLER.format(name=caller, leaf=leaf_name)

    response = authenticated.post(f"{TEMPLATES}/{caller}/graph", json={"yaml": text})

    assert response.status_code == HTTP_OK, response.text
    body: dict[str, object] = response.json()
    return body


def test_a_loop_carries_the_item_checkpoint_its_text_declares(
    caller_graph: dict[str, object],
) -> None:
    nodes = caller_graph["nodes"]
    assert isinstance(nodes, list)
    assert [node["id"] for node in nodes] == ["entries.call", "entries.after"]
    assert caller_graph["groups"] == [
        {
            "id": "entries",
            "label": "entries",
            "kind": "for_each",
            "members": ["entries.call", "entries.after"],
        }
    ]
    assert caller_graph["edges"] == [{"from": "entries.call", "to": "entries.after"}]

    after = next(node for node in nodes if node["id"] == "entries.after")
    assert after["kind"] == "checkpoint"
    assert after["gate"] == "human"
    assert after["human"] is True


def test_a_loop_collapses_its_call_to_the_stored_leaf(
    caller_graph: dict[str, object], leaf_name: str
) -> None:
    nodes = caller_graph["nodes"]
    assert isinstance(nodes, list)

    call = next(node for node in nodes if node["id"] == "entries.call")
    assert call["kind"] == "template"
    assert call["call"] == {"name": leaf_name, "version": 1}
    assert call["label"] == f"{leaf_name}@1"
    assert call["gate"] is None
