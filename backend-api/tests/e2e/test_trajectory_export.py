"""`GET /api/v1/projects/{id}/trajectories.jsonl` against the real stack (SPEC CAP-6, AD-19,
FR-32 export).

The filename, the count and the row ordering are settled without a database by
`tests/unit/application/test_trajectory_export.py` and `tests/unit/test_trajectories_router.py`.
What only Postgres settles is that the streamed response actually reaches an httpx client with
its headers intact, and that `trajectory_count` on `GET /projects/{id}` reads the same store the
export does.

There is no public write endpoint for a `trajectory` row (AD-19: `record_trajectory` is the
only writer, reached only from inside a Run's own commit-guard step), so — the same reason
`test_history.py` gives for its own shape — this module does not stage a Run. It creates a
fresh Project (which has none) for the empty-body and the count-is-zero claims, and reads
whatever trajectories the shared stack already has, shape-based and count-free, for the line
shape claim.
"""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest

HTTP_OK = 200
HTTP_NOT_FOUND = 404
PROBLEM = "application/problem+json"
NDJSON = "application/x-ndjson"
PROJECTS = "/api/v1/projects"
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"

LINE_FIELDS = frozenset(
    {
        "id",
        "run_id",
        "project_id",
        "repository_id",
        "story_id",
        "epic_index",
        "frame",
        "harness",
        "model",
        "attempts",
        "gate_results",
        "cost_usd",
        "tokens_in",
        "tokens_out",
        "wall_clock_seconds",
        "story_file",
        "start_sha",
        "end_sha",
        "human_actions",
        "recorded_at",
    }
)


@pytest.fixture
def unique_name() -> str:
    """A name no earlier run of this suite can have taken (`test_projects.py`'s own reason:
    there is no `DELETE`, so every run leaves its Projects behind)."""
    return f"e2e trajectory export {uuid4()}"


def create_project(client: httpx.Client, name: str) -> httpx.Response:
    return client.post(PROJECTS, json={"name": name})


def export_url(project_id: str) -> str:
    return f"{PROJECTS}/{project_id}/trajectories.jsonl"


def test_an_unknown_project_is_a_404_problem_document(authenticated: httpx.Client) -> None:
    response = authenticated.get(export_url(UNKNOWN_ID))

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"] == PROBLEM


def test_a_freshly_created_project_has_no_trajectories(
    authenticated: httpx.Client, unique_name: str
) -> None:
    project_id = create_project(authenticated, unique_name).json()["id"]

    response = authenticated.get(export_url(project_id))

    assert response.status_code == HTTP_OK
    assert response.content == b""


def test_the_headers_carry_ndjson_and_an_attachment_filename(
    authenticated: httpx.Client, unique_name: str
) -> None:
    created = create_project(authenticated, unique_name).json()

    response = authenticated.get(export_url(created["id"]))

    assert response.headers["content-type"].startswith(NDJSON)
    disposition = response.headers["content-disposition"]
    assert disposition.startswith(f'attachment; filename="trajectories-{created["slug"]}-')
    assert disposition.endswith('.jsonl"')


def test_the_project_read_models_own_count_matches_a_fresh_project(
    authenticated: httpx.Client, unique_name: str
) -> None:
    created = create_project(authenticated, unique_name).json()

    read = authenticated.get(f"{PROJECTS}/{created['id']}").json()

    assert read["trajectory_count"] == 0


def test_every_line_any_project_answers_parses_as_json_with_the_sm_fields(
    authenticated: httpx.Client,
) -> None:
    """Shape-based and count-free, the way `test_history.py` reads the shared stack: this
    suite creates Projects but never a Story that reaches `done`, so most Projects answer no
    lines at all — but whichever line a shared stack happens to have (the seeded `readiness`
    Project included) must be one JSON object with exactly these fields, newest first."""
    projects = authenticated.get(PROJECTS).json()["items"]

    for project in projects:
        response = authenticated.get(export_url(project["id"]))
        assert response.status_code == HTTP_OK
        lines = response.content.decode().splitlines()
        assert len(lines) == project["trajectory_count"]
        recorded_ats = []
        for line in lines:
            row = json.loads(line)
            assert set(row) == LINE_FIELDS
            assert row["project_id"] == project["id"]
            recorded_ats.append(row["recorded_at"])
        assert recorded_ats == sorted(recorded_ats, reverse=True)
