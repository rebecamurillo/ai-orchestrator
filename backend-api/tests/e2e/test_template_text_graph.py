"""`POST` and `GET /templates/{name}/graph` against the running stack (3.6).

The unit suite proves the shape over the fake repository. What only the real stack settles is
that the pair is mounted where the contract says, behind the one credential, and — the whole
reason the mount order is written down — that a three-segment `GET .../graph` reaches this
operation instead of being parsed as `version="graph"` by `GET /templates/{name}/{version}`.

The `POST` is asserted against text read back from the stack itself rather than against a
copy of a file pasted here: what the story claims is that posting a version's own text answers
that version's own graph.

Revised 2026-10-15 (Operator ruling: no test reads, runs or asserts on the shipped
`templates/*.yaml`; a test that needs a workflow brings its own). The stored versions read
back here are the suite's own epic and story fixtures (`tests/e2e/templates/`), posted under
names no earlier run can have taken; before this date they were `epic@1` and `story@1`.

The `POST` builds a graph and stores nothing, so the suite passes as many times against one
stack as it is run.
"""

from __future__ import annotations

from collections.abc import Iterator
from itertools import pairwise

import httpx
import pytest

from tests.e2e.helpers.templates import save_epic_pair

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422

TEMPLATES = "/api/v1/templates"

PROBLEM_MEDIA_TYPE = "application/problem+json"

BROKEN = "name: broken\nversion: 1\nsteps:\n  - id: sync\n    uses: no.such.kind\n"

#: `BROKEN`'s `uses:` line — the 422's `detail` names it.
BROKEN_LINE = 5

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
    epic, story = save_epic_pair(api, "e2e-text-graph")
    return {"epic": epic, "story": story}


def stored_yaml(client: httpx.Client, name: str, version: int) -> str:
    response = client.get(f"{TEMPLATES}/{name}/{version}")

    assert response.status_code == HTTP_OK
    return str(response.json()["yaml"])


def test_posting_a_stored_versions_own_text_answers_that_versions_graph(
    api: httpx.Client, names: dict[str, str]
) -> None:
    """The story's first acceptance criterion, over the really-stored story fixture."""
    story = names["story"]
    text = stored_yaml(api, story, 1)

    posted = api.post(f"{TEMPLATES}/{story}/graph", json={"yaml": text})

    assert posted.status_code == HTTP_OK
    assert posted.json() == api.get(f"{TEMPLATES}/{story}/1/graph").json()


def test_the_posted_graph_of_the_story_marks_its_agent_step(
    api: httpx.Client, names: dict[str, str]
) -> None:
    story = names["story"]
    text = stored_yaml(api, story, 1)

    body = api.post(f"{TEMPLATES}/{story}/graph", json={"yaml": text}).json()

    assert [node["id"] for node in body["nodes"] if node["agent"]] == ["build"]
    build = next(node for node in body["nodes"] if node["id"] == "build")
    assert build["gate"] == "liveness"


def test_posting_the_epics_text_answers_its_golden_shape(
    api: httpx.Client, names: dict[str, str]
) -> None:
    """The epic fixture is the one file with steps before and after a loop, a collapsed call
    and an item checkpoint — the shape 3.6's diagram is drawn from."""
    epic = names["epic"]
    text = stored_yaml(api, epic, 1)

    body = api.post(f"{TEMPLATES}/{epic}/graph", json={"yaml": text}).json()

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


def test_the_epics_nodes_carry_the_kind_label_and_gate_the_file_declares(
    api: httpx.Client, names: dict[str, str]
) -> None:
    """The ids alone are not the picture: kind, label and gate per node, as the fixture
    declares them (`web-client/tests/unit/diagram-fixtures.ts` draws the same shape)."""
    epic, story = names["epic"], names["story"]
    text = stored_yaml(api, epic, 1)

    body = api.post(f"{TEMPLATES}/{epic}/graph", json={"yaml": text}).json()

    assert [(node["kind"], node["label"], node["gate"]) for node in body["nodes"]] == [
        ("git.worktree", "checkout", "deterministic"),
        ("shell", "setup", "deterministic"),
        ("shell", "baseline", "deterministic"),
        ("agent", "spec-gate", "liveness"),
        # an unpinned call (Operator decision 2026-10-02, editable workflows)
        ("template", f"{story}@latest", None),
        ("checkpoint", "after", "human"),
        ("agent", "gen-e2e", "liveness"),
        ("git.commit", "commit-e2e", "deterministic"),
        ("shell", "e2e", "deterministic"),
        ("agent", "retro", "liveness"),
        ("git.commit", "commit-retro", "deterministic"),
        ("git.push", "push", "deterministic"),
        ("pr.link", "link", "liveness"),
        ("checkpoint", "done-checkpoint", "human"),
    ]
    assert [node["id"] for node in body["nodes"] if node["agent"]] == [
        "spec-gate",
        "gen-e2e",
        "retro",
    ]
    assert [node["id"] for node in body["nodes"] if node["human"]] == [
        "stories.after",
        "done-checkpoint",
    ]


def test_the_path_name_is_where_the_screen_is_open_not_what_is_graphed(
    api: httpx.Client, names: dict[str, str]
) -> None:
    """Stated as a decision rather than left to be discovered: the posted text is what is
    drawn, whatever the path segment says. The editor is free to hold a rename in progress,
    and `POST /templates/{name}/versions` is where the two are required to agree."""
    text = stored_yaml(api, names["epic"], 1)

    posted_elsewhere = api.post(f"{TEMPLATES}/{names['story']}/graph", json={"yaml": text})
    posted_here = api.post(f"{TEMPLATES}/{names['epic']}/graph", json={"yaml": text})

    assert posted_elsewhere.status_code == HTTP_OK
    assert posted_elsewhere.json() == posted_here.json()


def test_a_posted_call_is_resolved_against_the_real_repository(
    api: httpx.Client, names: dict[str, str]
) -> None:
    """The epic names its story unpinned (Operator decision 2026-10-02); nothing but the
    stack's own store can answer that the name exists."""
    text = stored_yaml(api, names["epic"], 1)

    body = api.post(f"{TEMPLATES}/{names['epic']}/graph", json={"yaml": text}).json()

    call = next(node for node in body["nodes"] if node["id"] == "stories.story")
    assert call["call"] == {"name": names["story"], "version": None}
    assert call["label"] == f"{names['story']}@latest"
    assert call["gate"] is None


def test_posting_text_that_does_not_validate_is_a_422_naming_the_line(
    api: httpx.Client, names: dict[str, str]
) -> None:
    response = api.post(f"{TEMPLATES}/{names['story']}/graph", json={"yaml": BROKEN})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["detail"] == f"line {BROKEN_LINE}: unknown kind"
    assert [error["reason"] for error in response.json()["errors"]] == ["unknown kind"]


def test_posting_a_graph_stores_no_version(api: httpx.Client, names: dict[str, str]) -> None:
    story = names["story"]
    before = api.get(f"{TEMPLATES}/{story}/versions").json()["items"]

    api.post(f"{TEMPLATES}/{story}/graph", json={"yaml": stored_yaml(api, story, 1)})

    assert api.get(f"{TEMPLATES}/{story}/versions").json()["items"] == before


def test_the_get_reaches_this_operation_and_not_the_version_route(
    api: httpx.Client, names: dict[str, str]
) -> None:
    """The story's second acceptance criterion, over the whole application: `graph` is a
    literal segment here, never a version number that fails to parse."""
    response = api.get(f"{TEMPLATES}/{names['story']}/graph")

    assert response.status_code == HTTP_OK
    assert response.json()["nodes"]


def test_the_get_answers_the_latest_stored_versions_graph(
    api: httpx.Client, names: dict[str, str]
) -> None:
    epic = names["epic"]
    latest = max(api.get(f"{TEMPLATES}/{epic}/versions").json()["items"])

    response = api.get(f"{TEMPLATES}/{epic}/graph")

    assert response.status_code == HTTP_OK
    assert response.json() == api.get(f"{TEMPLATES}/{epic}/{latest}/graph").json()


def test_an_unknown_name_is_a_404_problem_document(api: httpx.Client) -> None:
    response = api.get(f"{TEMPLATES}/does-not-exist/graph")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_without_the_bearer_both_operations_are_refused(
    client: httpx.Client, names: dict[str, str]
) -> None:
    read = client.get(f"{TEMPLATES}/{names['story']}/graph")
    built = client.post(f"{TEMPLATES}/{names['story']}/graph", json={"yaml": BROKEN})

    for response in (read, built):
        assert response.status_code == httpx.codes.UNAUTHORIZED
        assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
