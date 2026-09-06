"""`POST` and `GET /templates/{name}/graph` against the running stack (3.6).

The unit suite proves the shape over the fake repository. What only the real stack settles is
that the pair is mounted where the contract says, behind the one credential, and — the whole
reason the mount order is written down — that a three-segment `GET .../graph` reaches this
operation instead of being parsed as `version="graph"` by `GET /templates/{name}/{version}`.

The `POST` is asserted against text read back from the stack itself rather than against a
copy of a shipped file pasted here: what the story claims is that posting a version's own
text answers that version's own graph, and a fixture that merely happened to agree with the
seed would not be that claim.

Every request here is a read of the same kind: the `POST` builds a graph and stores nothing,
so the suite passes as many times against one stack as it is run.
"""

from __future__ import annotations

import httpx

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422

TEMPLATES = "/api/v1/templates"

PROBLEM_MEDIA_TYPE = "application/problem+json"

BROKEN = "name: broken\nversion: 1\nsteps:\n  - id: sync\n    uses: no.such.kind\n"

#: `BROKEN`'s `uses:` line — the 422's `detail` names it.
BROKEN_LINE = 5


def stored_yaml(client: httpx.Client, name: str, version: int) -> str:
    response = client.get(f"{TEMPLATES}/{name}/{version}")

    assert response.status_code == HTTP_OK
    return str(response.json()["yaml"])


def test_posting_a_stored_versions_own_text_answers_that_versions_graph(
    authenticated: httpx.Client,
) -> None:
    """The story's first acceptance criterion, over the really-seeded `story@1`."""
    text = stored_yaml(authenticated, "story", 1)

    posted = authenticated.post(f"{TEMPLATES}/story/graph", json={"yaml": text})

    assert posted.status_code == HTTP_OK
    assert posted.json() == authenticated.get(f"{TEMPLATES}/story/1/graph").json()


def test_the_posted_graph_of_story_1_marks_its_agent_step(authenticated: httpx.Client) -> None:
    text = stored_yaml(authenticated, "story", 1)

    body = authenticated.post(f"{TEMPLATES}/story/graph", json={"yaml": text}).json()

    assert [node["id"] for node in body["nodes"] if node["agent"]] == ["build"]
    build = next(node for node in body["nodes"] if node["id"] == "build")
    assert build["gate"] == "liveness"


def test_posting_epic_1s_text_answers_the_golden_shape(authenticated: httpx.Client) -> None:
    """`epic@1` is the one shipped file with steps before and after a loop, a collapsed call
    and an item checkpoint — the shape 3.6's diagram is drawn from."""
    text = stored_yaml(authenticated, "epic", 1)

    body = authenticated.post(f"{TEMPLATES}/epic/graph", json={"yaml": text}).json()

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


def test_epic_1s_nodes_carry_the_kind_label_and_gate_the_file_declares(
    authenticated: httpx.Client,
) -> None:
    """The ids alone are not the picture. `web-client/tests/unit/diagram-fixtures.ts` copies
    this graph to draw it without a stack; pinning kind, label and gate here is what makes the
    copy unable to drift from the real answer without one of the two suites failing."""
    text = stored_yaml(authenticated, "epic", 1)

    body = authenticated.post(f"{TEMPLATES}/epic/graph", json={"yaml": text}).json()

    assert [(node["kind"], node["label"], node["gate"]) for node in body["nodes"]] == [
        ("git.worktree", "checkout", "deterministic"),
        ("shell", "baseline", "deterministic"),
        ("template", "story@1", None),
        ("checkpoint", "after", "human"),
        ("git.push", "push", "deterministic"),
        ("pr.link", "link", "liveness"),
    ]
    assert [node["agent"] for node in body["nodes"]] == [False] * 6
    assert [node["human"] for node in body["nodes"]] == [
        False,
        False,
        False,
        True,
        False,
        False,
    ]


def test_the_path_name_is_where_the_screen_is_open_not_what_is_graphed(
    authenticated: httpx.Client,
) -> None:
    """Stated as a decision rather than left to be discovered: the posted text is what is
    drawn, whatever the path segment says. The editor is free to hold a rename in progress,
    and `POST /templates/{name}/versions` is where the two are required to agree."""
    text = stored_yaml(authenticated, "epic", 1)

    posted_elsewhere = authenticated.post(f"{TEMPLATES}/story/graph", json={"yaml": text})
    posted_here = authenticated.post(f"{TEMPLATES}/epic/graph", json={"yaml": text})

    assert posted_elsewhere.status_code == HTTP_OK
    assert posted_elsewhere.json() == posted_here.json()


def test_a_posted_call_is_resolved_against_the_real_repository(
    authenticated: httpx.Client,
) -> None:
    """`epic@1` names `story@1`; nothing but the stack's own store can answer that."""
    text = stored_yaml(authenticated, "epic", 1)

    body = authenticated.post(f"{TEMPLATES}/epic/graph", json={"yaml": text}).json()

    call = next(node for node in body["nodes"] if node["id"] == "stories.story")
    assert call["call"] == {"name": "story", "version": 1}
    assert call["label"] == "story@1"
    assert call["gate"] is None


def test_posting_text_that_does_not_validate_is_a_422_naming_the_line(
    authenticated: httpx.Client,
) -> None:
    response = authenticated.post(f"{TEMPLATES}/story/graph", json={"yaml": BROKEN})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["detail"] == f"line {BROKEN_LINE}: unknown kind"
    assert [error["reason"] for error in response.json()["errors"]] == ["unknown kind"]


def test_posting_a_graph_stores_no_version(authenticated: httpx.Client) -> None:
    before = authenticated.get(f"{TEMPLATES}/story/versions").json()["items"]

    authenticated.post(
        f"{TEMPLATES}/story/graph", json={"yaml": stored_yaml(authenticated, "story", 1)}
    )

    assert authenticated.get(f"{TEMPLATES}/story/versions").json()["items"] == before


def test_the_get_reaches_this_operation_and_not_the_version_route(
    authenticated: httpx.Client,
) -> None:
    """The story's second acceptance criterion, over the whole application: `graph` is a
    literal segment here, never a version number that fails to parse."""
    response = authenticated.get(f"{TEMPLATES}/story/graph")

    assert response.status_code == HTTP_OK
    assert response.json()["nodes"]


def test_the_get_answers_the_latest_stored_versions_graph(authenticated: httpx.Client) -> None:
    latest = max(authenticated.get(f"{TEMPLATES}/epic/versions").json()["items"])

    response = authenticated.get(f"{TEMPLATES}/epic/graph")

    assert response.status_code == HTTP_OK
    assert response.json() == authenticated.get(f"{TEMPLATES}/epic/{latest}/graph").json()


def test_an_unknown_name_is_a_404_problem_document(authenticated: httpx.Client) -> None:
    response = authenticated.get(f"{TEMPLATES}/does-not-exist/graph")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_without_the_bearer_both_operations_are_refused(client: httpx.Client) -> None:
    read = client.get(f"{TEMPLATES}/story/graph")
    built = client.post(f"{TEMPLATES}/story/graph", json={"yaml": BROKEN})

    for response in (read, built):
        assert response.status_code == httpx.codes.UNAUTHORIZED
        assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
