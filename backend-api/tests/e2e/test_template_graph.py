"""`GET /templates/{name}/{version}/graph` against the running stack (3.4).

The unit suite proves the shape over the fake repository. What only the real stack settles
is that the route is mounted where the contract says, behind the one credential, and that the
graph is built from the text the real repository actually stored.

Revised 2026-10-15 (Operator ruling: no test reads, runs or asserts on the shipped
`templates/*.yaml`; a test that needs a workflow brings its own). Every graph here is read
off the suite's own fixtures — `tests/e2e/templates/`, posted under names no earlier run can
have taken — so the golden shapes below pin files this suite owns and nothing the Operator
edits. Before this date they pinned `epic@1`, `story@1` and `repo-init@1`.

The epic fixture is the case worth asserting whole: steps before and after a loop, a collapsed
unpinned call, and an item checkpoint, all in one file.
"""

from __future__ import annotations

from collections.abc import Iterator
from itertools import pairwise

import httpx
import pytest

from tests.e2e.helpers.templates import save_epic_pair, save_repo_init

HTTP_OK = 200
HTTP_NOT_FOUND = 404

TEMPLATES = "/api/v1/templates"

PROBLEM_MEDIA_TYPE = "application/problem+json"

#: The repo-init fixture: eight steps and no loop.
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

#: The epic fixture's node ids, in file order.
EPIC_NODES = [
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


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=10.0) as client:
        yield client


@pytest.fixture(scope="module")
def names(api: httpx.Client) -> dict[str, str]:
    """The suite's own epic, story and repo-init, stored once for the module."""
    epic, story = save_epic_pair(api, "e2e-graph")
    return {"epic": epic, "story": story, "repo_init": save_repo_init(api, "e2e-graph-init")}


def graph_of(api: httpx.Client, name: str, version: int = 1) -> dict[str, object]:
    response = api.get(f"{TEMPLATES}/{name}/{version}/graph")
    assert response.status_code == HTTP_OK, response.text
    body: dict[str, object] = response.json()
    return body


def test_the_epic_fixture_answers_its_golden_shape(
    api: httpx.Client, names: dict[str, str]
) -> None:
    body = graph_of(api, names["epic"])

    assert [node["id"] for node in body["nodes"]] == EPIC_NODES
    assert body["groups"] == [
        {
            "id": "stories",
            "label": "stories",
            "kind": "for_each",
            "members": ["stories.story", "stories.after"],
        }
    ]
    assert body["edges"] == [
        {"from": before, "to": after} for before, after in pairwise(EPIC_NODES)
    ]


def test_the_epic_fixture_collapses_its_unpinned_call_to_the_story(
    api: httpx.Client, names: dict[str, str]
) -> None:
    body = graph_of(api, names["epic"])

    call = next(node for node in body["nodes"] if node["id"] == "stories.story")
    assert call["kind"] == "template"
    # an unpinned call resolves at plan time and reads `version: None` (Operator decision
    # 2026-10-02, editable workflows)
    assert call["call"] == {"name": names["story"], "version": None}
    assert call["label"] == f"{names['story']}@latest"
    assert call["gate"] is None


def test_the_epic_fixture_marks_its_item_checkpoint_human(
    api: httpx.Client, names: dict[str, str]
) -> None:
    body = graph_of(api, names["epic"])

    after = next(node for node in body["nodes"] if node["id"] == "stories.after")
    assert after["kind"] == "checkpoint"
    assert after["gate"] == "human"
    assert after["human"] is True


def test_the_story_fixture_marks_its_agent_step(api: httpx.Client, names: dict[str, str]) -> None:
    body = graph_of(api, names["story"])

    assert [node["id"] for node in body["nodes"] if node["agent"]] == ["build"]
    build = next(node for node in body["nodes"] if node["id"] == "build")
    assert build["gate"] == "liveness"


def test_the_repo_init_fixture_is_eight_nodes_chained_with_no_group(
    api: httpx.Client, names: dict[str, str]
) -> None:
    body = graph_of(api, names["repo_init"])

    assert [node["id"] for node in body["nodes"]] == REPO_INIT_NODES
    assert body["groups"] == []
    assert len(body["edges"]) == len(REPO_INIT_NODES) - 1


def test_no_stored_node_id_carries_an_index(api: httpx.Client, names: dict[str, str]) -> None:
    """AD-15: an id is joinable to `unvalidated` and stable across items — over every stored
    version the stack lists, this module's own fixtures among them."""
    listed = api.get(TEMPLATES).json()["items"]
    assert {item["name"] for item in listed} >= set(names.values())

    for item in listed:
        for version in item["versions"]:
            body = graph_of(api, item["name"], version)

            for node in body["nodes"]:
                assert "[" not in node["id"] and "]" not in node["id"], node
                assert not any(part.isdigit() for part in node["id"].split(".")), node


def test_an_unknown_version_is_a_404_problem_document(
    api: httpx.Client, names: dict[str, str]
) -> None:
    response = api.get(f"{TEMPLATES}/{names['epic']}/9/graph")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_an_unknown_name_is_a_404_problem_document(api: httpx.Client) -> None:
    response = api.get(f"{TEMPLATES}/does-not-exist/1/graph")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_without_the_bearer_the_graph_is_refused(
    client: httpx.Client, names: dict[str, str]
) -> None:
    response = client.get(f"{TEMPLATES}/{names['epic']}/1/graph")

    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
