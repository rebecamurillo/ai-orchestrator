"""`POST`/`GET /api/v1/runs` against the running stack (SPEC CAP-4, FR-6, FR-8).

The rules are proven over fakes in `tests/unit/application/test_create_run_use_case.py`;
what only a real Postgres and a real `git` settle is the claim this story exists for: that
a Run and its `step_run` rows land together, through the real adapters (4.1's flush-per-
insert ordering), that `pinned_by` (4.4) is a real `jsonb` containment query rather than a
Python scan, and that the placeholder `WorkflowEngine` (`infrastructure/engine/local.py`)
is actually wired so `POST /runs` answers for real.

Every Template here is a fresh name of its own — `e2e-leaf-<uuid>` — the same convention
`test_templates.py` uses, and for the same reason: this suite may run twice against the
same stack, and a Run that pinned a shipped Template (`repo-init`, `epic`, `story`,
`initiative`) would permanently raise its `pinned_by` for the rest of that stack's life,
which would break `test_templates.py`'s own frozen `pinned_by == 0` assertions for them.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import Fixtures, manifest_stating

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NOT_FOUND = 404
HTTP_UNAUTHORIZED = 401

PROJECTS = "/api/v1/projects"
REPOSITORIES = "/api/v1/repositories"
TEMPLATES = "/api/v1/templates"
RUNS = "/api/v1/runs"

BRANCH = "main"

LEAF = (
    "name: {name}\nversion: 1\ndescription: e2e leaf\n"
    "inputs:\n"
    "  project:     {{ type: project,    required: true }}\n"
    "  repository:  {{ type: repository, required: true }}\n"
    "  base_branch: {{ type: string,     required: true }}\n"
    "steps:\n"
    "  - id: touch\n"
    "    uses: shell\n"
    "    with: {{ command: 'true' }}\n"
    "    gate: deterministic\n"
)


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def fixtures(settings: Settings) -> Fixtures:
    return Fixtures(settings.work_dir)


@pytest.fixture
def leaf_name() -> str:
    return f"e2e-leaf-{uuid4().hex}"


def save_template(client: httpx.Client, name: str) -> dict[str, object]:
    response = client.post(f"{TEMPLATES}/{name}/versions", json={"yaml": LEAF.format(name=name)})
    assert response.status_code == HTTP_CREATED, response.text
    body: dict[str, object] = response.json()
    return body


def create_project(client: httpx.Client) -> str:
    response = client.post(PROJECTS, json={"name": f"e2e run creation {uuid4()}"})
    assert response.status_code == HTTP_CREATED, response.text
    return str(response.json()["id"])


def create_repository(
    client: httpx.Client, project_id: str, url: str, *, default_branch: str = BRANCH
) -> str:
    response = client.post(
        f"{PROJECTS}/{project_id}/repositories",
        json={"url": url, "default_branch": default_branch},
    )
    assert response.status_code == HTTP_CREATED, response.text
    return str(response.json()["id"])


def clone_check(client: httpx.Client, repository_id: str) -> None:
    response = client.post(f"{REPOSITORIES}/{repository_id}/clone-check")
    assert response.status_code == HTTP_OK, response.text
    assert response.json()["status"] == "ok", response.json()


@pytest.fixture
def repository_id(authenticated: httpx.Client, fixtures: Fixtures, settings: Settings) -> str:
    """A Project, a real bare repository stating the running `bmad_version`, clone-checked."""
    project_id = create_project(authenticated)
    url = fixtures.make(manifest_stating(settings.bmad_version))
    repository_id = create_repository(authenticated, project_id, url)
    clone_check(authenticated, repository_id)
    return repository_id


def run_payload(name: str, repository_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "template_name": name,
        "template_version": 1,
        "repository_id": repository_id,
        "base_branch": BRANCH,
        "budget_usd": "5",
    }
    payload.update(overrides)
    return payload


def project_id_of(authenticated: httpx.Client, repository_id: str) -> str:
    body = authenticated.get(f"{REPOSITORIES}/{repository_id}").json()
    return str(body["project_id"])


# ── the whole path: create, persist, enqueue, read back ─────────────────────────────────


def test_a_passing_run_persists_pins_and_enqueues(
    authenticated: httpx.Client, repository_id: str, leaf_name: str
) -> None:
    save_template(authenticated, leaf_name)
    project_id = project_id_of(authenticated, repository_id)
    payload = run_payload(leaf_name, repository_id, project_id=project_id)

    response = authenticated.post(RUNS, json=payload)

    assert response.status_code == HTTP_CREATED, response.text
    body = response.json()
    assert body["starts_now"] is True
    assert body["waiting"] == "starts immediately if the repository is free"
    run = body["run"]
    assert run["status"] == "queued"
    assert run["template"] == leaf_name
    assert run["version"] == 1
    assert run["budget_usd"] == "5.000000"

    version = authenticated.get(f"{TEMPLATES}/{leaf_name}/1").json()
    assert version["pinned_by"] == 1


def test_get_reads_back_the_created_run(
    authenticated: httpx.Client, repository_id: str, leaf_name: str
) -> None:
    save_template(authenticated, leaf_name)
    project_id = project_id_of(authenticated, repository_id)
    created = authenticated.post(
        RUNS, json=run_payload(leaf_name, repository_id, project_id=project_id)
    ).json()

    response = authenticated.get(f"{RUNS}/{created['run']['id']}")

    assert response.status_code == HTTP_OK
    assert response.json() == created["run"]


def test_a_second_run_against_the_same_repository_waits(
    authenticated: httpx.Client, repository_id: str, leaf_name: str
) -> None:
    save_template(authenticated, leaf_name)
    project_id = project_id_of(authenticated, repository_id)
    payload = run_payload(leaf_name, repository_id, project_id=project_id)
    first = authenticated.post(RUNS, json=payload)
    assert first.status_code == HTTP_CREATED, first.text

    second = authenticated.post(RUNS, json=payload)

    assert second.status_code == HTTP_CREATED, second.text
    assert second.json()["starts_now"] is False
    assert "queues behind" in second.json()["waiting"]


def test_an_unknown_repository_is_a_404(authenticated: httpx.Client, leaf_name: str) -> None:
    project_id = create_project(authenticated)
    save_template(authenticated, leaf_name)
    unknown = "01a06887-79ab-759b-97a0-71c32ad939c2"

    response = authenticated.post(RUNS, json=run_payload(leaf_name, unknown, project_id=project_id))

    assert response.status_code == HTTP_NOT_FOUND


HTTP_UNPROCESSABLE = 422


def test_a_zero_budget_is_a_422_not_a_server_error(
    authenticated: httpx.Client, repository_id: str, leaf_name: str
) -> None:
    save_template(authenticated, leaf_name)
    project_id = project_id_of(authenticated, repository_id)
    payload = run_payload(leaf_name, repository_id, project_id=project_id, budget_usd="0")

    response = authenticated.post(RUNS, json=payload)

    assert response.status_code == HTTP_UNPROCESSABLE, response.text


def test_both_operations_need_the_bearer(client: httpx.Client) -> None:
    for call in (
        lambda: client.post(RUNS, json={}),
        lambda: client.get(RUNS),
        lambda: client.get(f"{RUNS}/01a06887-79ab-759b-97a0-71c32ad939c2"),
    ):
        response = call()
        assert response.status_code == HTTP_UNAUTHORIZED


def test_no_response_this_suite_saw_carries_the_instance_token(
    authenticated: httpx.Client, repository_id: str, leaf_name: str, token: str
) -> None:
    save_template(authenticated, leaf_name)
    project_id = project_id_of(authenticated, repository_id)
    body = authenticated.post(
        RUNS, json=run_payload(leaf_name, repository_id, project_id=project_id)
    ).text

    assert token not in body
