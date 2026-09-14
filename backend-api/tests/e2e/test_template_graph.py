"""`GET /templates/{name}/{version}/graph` against the running stack (3.4).

The unit suite proves the shape over the fake repository. What only the real stack settles
is that the route is mounted where the contract says, behind the one credential, and that the
graph is built from the text the real seeding actually stored — through the real repository,
the real `TEMPLATES_DIR` — rather than from a fixture that happens to agree with it.

Every read here is a read: no `POST`, no name of its own, nothing to clean up, so the suite
passes as many times against one stack as it is run.

`epic@1` is the case worth asserting whole. It is the only shipped Template with all four
features at once — steps before and after a loop, a collapsed call, and an item checkpoint —
so its node list, its group and its edges are pinned here exactly as the story's golden shape
states them.
"""

from __future__ import annotations

import httpx

HTTP_OK = 200
HTTP_NOT_FOUND = 404

TEMPLATES = "/api/v1/templates"

PROBLEM_MEDIA_TYPE = "application/problem+json"

#: `repo-init@1` ships seven steps and no loop.
REPO_INIT_NODES = [
    "checkout",
    "install",
    "context",
    "context-review",
    "commit",
    "push",
    "link",
]


def test_epic_1_answers_the_golden_shape(authenticated: httpx.Client) -> None:
    response = authenticated.get(f"{TEMPLATES}/epic/1/graph")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert [node["id"] for node in body["nodes"]] == [
        "checkout",
        "baseline",
        "stories.story",
        "stories.after",
        "push",
        "link",
    ]
    assert body["groups"] == [
        {
            "id": "stories",
            "label": "stories",
            "kind": "for_each",
            "members": ["stories.story", "stories.after"],
        }
    ]
    assert body["edges"] == [
        {"from": "checkout", "to": "baseline"},
        {"from": "baseline", "to": "stories.story"},
        {"from": "stories.story", "to": "stories.after"},
        {"from": "stories.after", "to": "push"},
        {"from": "push", "to": "link"},
    ]


def test_epic_1_collapses_its_call_to_story(authenticated: httpx.Client) -> None:
    body = authenticated.get(f"{TEMPLATES}/epic/1/graph").json()

    call = next(node for node in body["nodes"] if node["id"] == "stories.story")
    assert call["kind"] == "template"
    assert call["call"] == {"name": "story", "version": 1}
    assert call["label"] == "story@1"
    assert call["gate"] is None


def test_epic_1_marks_its_item_checkpoint_human(authenticated: httpx.Client) -> None:
    body = authenticated.get(f"{TEMPLATES}/epic/1/graph").json()

    after = next(node for node in body["nodes"] if node["id"] == "stories.after")
    assert after["kind"] == "checkpoint"
    assert after["gate"] == "human"
    assert after["human"] is True


def test_story_1_marks_its_agent_step(authenticated: httpx.Client) -> None:
    body = authenticated.get(f"{TEMPLATES}/story/1/graph").json()

    assert [node["id"] for node in body["nodes"] if node["agent"]] == ["build"]
    build = next(node for node in body["nodes"] if node["id"] == "build")
    assert build["gate"] == "liveness"


def test_repo_init_1_is_seven_nodes_chained_with_no_group(authenticated: httpx.Client) -> None:
    body = authenticated.get(f"{TEMPLATES}/repo-init/1/graph").json()

    assert [node["id"] for node in body["nodes"]] == REPO_INIT_NODES
    assert body["groups"] == []
    assert len(body["edges"]) == len(REPO_INIT_NODES) - 1


def test_initiative_1_carries_the_item_checkpoint_the_stored_text_declares(
    authenticated: httpx.Client,
) -> None:
    """The one shipped file this story edited, read back through storage rather than off
    disk. `_seed_file` inserts changed text as the *next* version, so a stack that already
    held the pre-edit `initiative` would answer this version without its item checkpoint —
    the unit twin, which reads `templates/initiative.yaml` directly, cannot see that."""
    response = authenticated.get(f"{TEMPLATES}/initiative/1/graph")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert [node["id"] for node in body["nodes"]] == ["epics.epic", "epics.after"]
    assert body["groups"] == [
        {
            "id": "epics",
            "label": "epics",
            "kind": "for_each",
            "members": ["epics.epic", "epics.after"],
        }
    ]
    assert body["edges"] == [{"from": "epics.epic", "to": "epics.after"}]


def test_initiative_1_collapses_its_call_to_epic(authenticated: httpx.Client) -> None:
    body = authenticated.get(f"{TEMPLATES}/initiative/1/graph").json()

    call = next(node for node in body["nodes"] if node["id"] == "epics.epic")
    assert call["call"] == {"name": "epic", "version": 1}
    assert call["label"] == "epic@1"


def test_no_shipped_node_id_carries_an_index(authenticated: httpx.Client) -> None:
    """AD-15: an id is joinable to `unvalidated` and stable across items."""
    for name in ("repo-init", "story", "epic", "initiative"):
        body = authenticated.get(f"{TEMPLATES}/{name}/1/graph").json()

        for node in body["nodes"]:
            assert "[" not in node["id"] and "]" not in node["id"], node
            assert not any(part.isdigit() for part in node["id"].split(".")), node


def test_an_unknown_version_is_a_404_problem_document(authenticated: httpx.Client) -> None:
    response = authenticated.get(f"{TEMPLATES}/epic/9/graph")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_an_unknown_name_is_a_404_problem_document(authenticated: httpx.Client) -> None:
    response = authenticated.get(f"{TEMPLATES}/does-not-exist/1/graph")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_without_the_bearer_the_graph_is_refused(client: httpx.Client) -> None:
    response = client.get(f"{TEMPLATES}/epic/1/graph")

    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
