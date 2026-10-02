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
    "setup",
    "install",
    "context",
    "context-review",
    "commit",
    "push",
    "link",
]


def test_epic_1_answers_the_golden_shape(authenticated: httpx.Client) -> None:
    """Operator revision 2026-09-15: the quality-gate reorder (b0f3898 — unit on story,
    e2e on epic) gave `epic@1` a `setup` step and an `e2e` step; this golden shape follows
    the shipped file it mirrors. Stories 4-4..4-7 (2026-09-17) added `spec-gate`, the
    `gen-e2e`/`commit-e2e` pair, `retro`/`commit-retro` and the final `done-checkpoint`;
    the shape follows again."""
    response = authenticated.get(f"{TEMPLATES}/epic/1/graph")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert [node["id"] for node in body["nodes"]] == [
        "checkout",
        "setup",
        "baseline",
        "spec-gate",
        "stories.story",
        "stories.after",
        "gen-e2e",
        "commit-e2e",
        "e2e",
        "retro",
        "commit-retro",
        "push",
        "link",
        "done-checkpoint",
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
        {"from": "checkout", "to": "setup"},
        {"from": "setup", "to": "baseline"},
        {"from": "baseline", "to": "spec-gate"},
        {"from": "spec-gate", "to": "stories.story"},
        {"from": "stories.story", "to": "stories.after"},
        {"from": "stories.after", "to": "gen-e2e"},
        {"from": "gen-e2e", "to": "commit-e2e"},
        {"from": "commit-e2e", "to": "e2e"},
        {"from": "e2e", "to": "retro"},
        {"from": "retro", "to": "commit-retro"},
        {"from": "commit-retro", "to": "push"},
        {"from": "push", "to": "link"},
        {"from": "link", "to": "done-checkpoint"},
    ]


def test_epic_1_collapses_its_call_to_story(authenticated: httpx.Client) -> None:
    body = authenticated.get(f"{TEMPLATES}/epic/1/graph").json()

    call = next(node for node in body["nodes"] if node["id"] == "stories.story")
    assert call["kind"] == "template"
    # Operator decision 2026-10-02 (editable workflows, unpinned callees): the shipped `epic`
    # file no longer pins `story`, so the call resolves at plan time and reads `version: None`
    assert call["call"] == {"name": "story", "version": None}
    assert call["label"] == "story@latest"
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


def test_repo_init_1_is_eight_nodes_chained_with_no_group(authenticated: httpx.Client) -> None:
    body = authenticated.get(f"{TEMPLATES}/repo-init/1/graph").json()

    assert [node["id"] for node in body["nodes"]] == REPO_INIT_NODES
    assert body["groups"] == []
    assert len(body["edges"]) == len(REPO_INIT_NODES) - 1


# Revised 2026-09-30 (Operator decision: the mono-repo `initiative` and `story-run` workflows
# are retired to `templates/drafts/`, no longer seeded). The two `initiative@1` reads that
# stood here — its loop group with the `.after` item checkpoint, and its collapsed call to
# `epic@1` — now live in `test_template_graph_loop.py`, asserted over a caller of that suite's
# own so no shipped file is pinned (hard rule 6).


def test_no_stored_node_id_carries_an_index(authenticated: httpx.Client) -> None:
    """AD-15: an id is joinable to `unvalidated` and stable across items. Revised 2026-09-30
    (Operator decision: `initiative` retired to `templates/drafts/`): every stored version
    the stack lists, shipped or posted, rather than four listed names."""
    listed = authenticated.get(TEMPLATES).json()["items"]
    assert listed

    for item in listed:
        for version in item["versions"]:
            body = authenticated.get(f"{TEMPLATES}/{item['name']}/{version}/graph").json()

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
