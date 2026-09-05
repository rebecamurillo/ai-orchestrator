"""The two clone-check operations over an ASGI transport, and the check a save runs.

The rules are asserted in `tests/unit/test_clone_check_use_cases.py`; what only a request can
show is here: which status each operation answers with, that the `GET` reads the stored
result and runs no git command at all, that a save runs one check per Repository *after* it
has committed — so a failing check answers 200 and leaves both Repositories stored — and that
the response body carries the whole result rather than the four keys a Repository read does.

`dependency_overrides` replaces `project_ports` with the fakes (AD-18), so no database, no
key and no process are involved.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import project_ports
from orchestrator.api.routers import clone_check as router_module
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.project import Project, slugify
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import CloneResult, GitError, RemoteRef
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_CREATED = 201
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROJECTS = "/api/v1/projects"
REPOSITORIES = "/api/v1/repositories"
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"

SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
MANIFEST = "installation:\n  version: 6.11.0\n"
NOT_FOUND_OUTPUT = "remote: Repository not found."

FOUR = 4
TWO = 2


def clone_check_url(repository_id: str) -> str:
    return f"{REPOSITORIES}/{repository_id}/clone-check"


def test_the_router_declares_the_two_operations_and_repeats_no_dependency() -> None:
    """A router of its own, so `repositories.py` keeps declaring exactly its four; the
    bearer is still attached to the whole `/api/v1` prefix by `main.py` (AD-4)."""
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert sorted(routes) == [
        (["GET"], router_module.CLONE_CHECK_PATH),
        (["POST"], router_module.CLONE_CHECK_PATH),
    ]
    for route in router_module.router.routes:
        assert route.dependencies == []


def reachable(times: int = 4) -> FakeGit:
    """A remote that answers everything, for as many Repositories as a test registers."""
    return FakeGit(
        ls_remote=[RemoteRef(ref="HEAD", sha=SHA), RemoteRef(ref="refs/heads/main", sha=SHA)]
        * times,
        clone_base=[CloneResult(seconds=1.0, bytes=4096)],
        read_file=[MANIFEST],
    )


class Harness:
    """One application, one set of fakes including a scripted `Git`, and a bearer client."""

    def __init__(self, env: dict[str, str], git: FakeGit | None = None) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.uow = FakeUnitOfWork()
        self.projects = FakeProjectRepository()
        self.repositories = FakeRepositoryRepository()
        self.crypto = FakeCrypto()
        self.clock = FakeClock()
        self.git = git or reachable()
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[project_ports] = self._ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _ports(self) -> ProjectPorts:
        if not self.uow.calls or self.uow.calls[-1] == "exit":
            self.uow.__enter__()
        return ProjectPorts(
            uow=self.uow,
            projects=self.projects,
            repositories=self.repositories,
            crypto=self.crypto,
            clock=self.clock,
            git=self.git,
        )

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def project(self, name: str = "My Website") -> UUID:
        project = Project(
            id=new_id(),
            slug=slugify(name),
            name=name,
            context_text="",
            context_paths=(),
            env_vars_enc=(),
            log_prompt_content=False,
            created_at=self.clock.now(),
            updated_at=self.clock.now(),
        )
        self.projects.add(project)
        return project.id


@pytest.fixture
def api(env: dict[str, str]) -> Harness:
    return Harness(env)


async def add_repository(api: Harness, project_id: UUID, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": "https://github.com/org/my-repo.git",
        "default_branch": "main",
    }
    payload.update(overrides)
    async with api.client() as client:
        response = await client.post(f"{PROJECTS}/{project_id}/repositories", json=payload)
    assert response.status_code == HTTP_CREATED, response.text
    body: dict[str, Any] = response.json()
    return body


async def client_put(api: Harness, project_id: UUID) -> httpx.Response:
    async with api.client() as client:
        return await client.put(f"{PROJECTS}/{project_id}", json={"name": "My Website"})


# ── running a check ──────────────────────────────────────────────────────────


async def test_a_check_answers_200_with_the_whole_result(api: Harness) -> None:
    repository = await add_repository(api, api.project())

    async with api.client() as client:
        response = await client.post(clone_check_url(repository["id"]))

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["status"] == "ok"
    assert len(body["lines"]) == FOUR
    assert body["bmad_version"] == api.settings.bmad_version
    assert body["hint"] == ""


async def test_the_result_shape_is_the_one_the_contract_publishes(api: Harness) -> None:
    repository = await add_repository(api, api.project())

    async with api.client() as client:
        body = (await client.post(clone_check_url(repository["id"]))).json()

    assert set(body) == {"status", "at", "output", "bmad_version", "lines", "hint"}
    assert set(body["lines"][0]) == {"name", "status", "seconds", "output"}


async def test_the_check_clones_under_the_configured_work_dir(api: Harness) -> None:
    """`WORK_DIR` is read once, by the settings object, and reaches the use case as a path."""
    repository = await add_repository(api, api.project())

    async with api.client() as client:
        await client.post(clone_check_url(repository["id"]))

    cloned = api.git.called("clone_base")[0][1]
    assert str(cloned).startswith(str(api.settings.work_dir))
    assert cloned.name == "base"


async def test_a_failing_check_is_a_200_carrying_the_failure(env: dict[str, str]) -> None:
    """A check that failed is an answer, not an error: the request itself worked."""
    error = GitError(command="git ls-remote", exit_code=128, output=NOT_FOUND_OUTPUT)
    api = Harness(env, FakeGit(ls_remote=[error]))
    repository = await add_repository(api, api.project())

    async with api.client() as client:
        response = await client.post(clone_check_url(repository["id"]))

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["status"] == "failed"
    assert body["output"] == NOT_FOUND_OUTPUT
    assert body["hint"]


async def test_a_check_on_an_unknown_repository_is_a_404(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post(clone_check_url(UNKNOWN_ID))

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["title"] == "not found"


async def test_a_check_on_an_id_that_is_not_a_uuid_is_a_422(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post(clone_check_url("not-a-uuid"))

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


# ── reading the stored result ────────────────────────────────────────────────


async def test_reading_a_repository_that_was_never_checked_answers_pending(
    api: Harness,
) -> None:
    repository = await add_repository(api, api.project())

    async with api.client() as client:
        response = await client.get(clone_check_url(repository["id"]))

    assert response.status_code == HTTP_OK
    assert response.json()["status"] == "pending"
    assert response.json()["lines"] == []


async def test_reading_runs_no_git_command_at_all(api: Harness) -> None:
    """A read that re-ran the check would make every page load a clone."""
    repository = await add_repository(api, api.project())

    async with api.client() as client:
        await client.get(clone_check_url(repository["id"]))

    assert api.git.calls == []


async def test_reading_answers_the_result_the_last_check_stored(api: Harness) -> None:
    repository = await add_repository(api, api.project())

    async with api.client() as client:
        ran = await client.post(clone_check_url(repository["id"]))
        read = await client.get(clone_check_url(repository["id"]))

    assert read.json() == ran.json()


async def test_reading_an_unknown_repository_is_a_404(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(clone_check_url(UNKNOWN_ID))

    assert response.status_code == HTTP_NOT_FOUND


async def test_both_operations_need_the_bearer(api: Harness) -> None:
    transport = httpx.ASGITransport(app=api.app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        for method in ("get", "post"):
            response = await client.request(method, clone_check_url(UNKNOWN_ID))

            assert response.status_code == HTTP_UNAUTHORIZED, method


# ── what a Repository read publishes ─────────────────────────────────────────


async def test_a_checked_repository_read_carries_the_lines_beside_the_check(
    api: Harness,
) -> None:
    repository = await add_repository(api, api.project())

    async with api.client() as client:
        await client.post(clone_check_url(repository["id"]))
        body = (await client.get(f"{REPOSITORIES}/{repository['id']}")).json()

    assert set(body["clone_check"]) == {"status", "at", "output", "bmad_version"}
    assert len(body["clone_check_lines"]) == FOUR
    assert body["clone_check_hint"] == ""


# ── the check a save runs ────────────────────────────────────────────────────


async def test_creating_a_project_answers_201_and_checks_nothing_yet(api: Harness) -> None:
    """A new Project holds no Repository, so there is nothing to check."""
    async with api.client() as client:
        response = await client.post(PROJECTS, json={"name": "Fresh"})

    assert response.status_code == HTTP_CREATED
    assert api.git.calls == []


async def test_updating_a_project_checks_every_repository_it_holds(api: Harness) -> None:
    project_id = api.project()
    await add_repository(api, project_id, url="https://github.com/org/one.git")
    await add_repository(api, project_id, url="https://github.com/org/two.git")

    async with api.client() as client:
        response = await client.put(f"{PROJECTS}/{project_id}", json={"name": "My Website"})

    assert response.status_code == HTTP_OK
    assert len(api.git.called("clone_base")) == TWO
    assert [item["clone_check"]["status"] for item in response.json()["repositories"]] == [
        "ok",
        "ok",
    ]


async def test_a_repository_whose_check_failed_still_saves_the_project(
    env: dict[str, str],
) -> None:
    """The acceptance criterion: one reachable, one that exists nowhere, and a 200."""
    error = GitError(command="git ls-remote", exit_code=128, output=NOT_FOUND_OUTPUT)
    git = FakeGit(
        ls_remote=[
            RemoteRef(ref="HEAD", sha=SHA),
            RemoteRef(ref="refs/heads/main", sha=SHA),
            error,
        ],
        read_file=[MANIFEST],
    )
    api = Harness(env, git)
    project_id = api.project()
    await add_repository(api, project_id, url="https://github.com/org/good.git")
    await add_repository(api, project_id, url="https://github.com/org/bad.git")

    async with api.client() as client:
        response = await client.put(f"{PROJECTS}/{project_id}", json={"name": "My Website"})

    assert response.status_code == HTTP_OK
    good, bad = response.json()["repositories"]
    assert good["clone_check"]["status"] == "ok"
    assert len(good["clone_check_lines"]) == FOUR
    assert good["clone_check"]["bmad_version"] == api.settings.bmad_version
    assert bad["clone_check"]["status"] == "failed"
    assert bad["clone_check"]["output"] == NOT_FOUND_OUTPUT
    assert bad["clone_check_lines"][0]["status"] == "failed"
    assert bad["clone_check_hint"]


async def test_a_save_survives_a_failure_that_is_not_gits(env: dict[str, str]) -> None:
    """An unwritable `WORK_DIR` is an `OSError`, not a `GitError`. Escaping here would
    answer a 500 for a `PUT` whose Project and Repositories were already committed."""
    api = Harness(env, FakeGit(clone_base=[PermissionError(13, "Permission denied", "/work")]))
    project_id = api.project()
    await add_repository(api, project_id)

    response = await client_put(api, project_id)

    assert response.status_code == HTTP_OK, response.text
    stored = response.json()["repositories"][0]
    assert stored["clone_check"]["status"] == "failed"
    assert "PermissionError" in stored["clone_check"]["output"]


async def test_running_a_check_over_a_failure_that_is_not_gits_is_still_a_200(
    env: dict[str, str],
) -> None:
    api = Harness(env, FakeGit(ls_remote=[FileNotFoundError(2, "No such file", "git")]))
    repository = await add_repository(api, api.project())

    async with api.client() as client:
        response = await client.post(clone_check_url(repository["id"]))

    assert response.status_code == HTTP_OK
    assert response.json()["status"] == "failed"
    assert "FileNotFoundError" in response.json()["output"]


async def test_the_result_of_a_saves_check_is_what_a_later_read_answers(api: Harness) -> None:
    """The save commits the results; nothing has to re-run to see them."""
    project_id = api.project()
    repository = await add_repository(api, project_id)

    async with api.client() as client:
        await client.put(f"{PROJECTS}/{project_id}", json={"name": "My Website"})
        read = await client.get(clone_check_url(repository["id"]))

    assert read.json()["status"] == "ok"
