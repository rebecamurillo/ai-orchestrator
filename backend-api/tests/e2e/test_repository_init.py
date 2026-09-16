"""`POST /repositories/{id}/init` end to end (SPEC CAP-10, FR-30): the epic's own success
signal, from the Project screen's side rather than `POST /runs`'s.

`tests/e2e/test_repo_init.py` already proves `repo-init@1` runs `plan -> checkout -> install
-> commit -> push -> link` for real; this module proves the two things only this endpoint
adds: the two refusals (a failed clone check, a `repo-init` Run already going), and the
completion hook — that a finished Run re-runs the Repository's own clone check, so `GET
/projects/{id}` reads the installed version and the compare link without the Operator
re-running the check by hand (the brief's own `[ASSUMPTION]`), and lists the Run `DON`.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import Fixtures
from tests.e2e.test_run_creation import clone_check, create_project, create_repository

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409

PROJECTS = "/api/v1/projects"
REPOSITORIES = "/api/v1/repositories"

RUN_TIMEOUT_SECONDS = 900.0
POLL_INTERVAL_SECONDS = 2.0

TEMPLATE = "repo-init"
DONE = "DON"


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=10.0) as client:
        yield client


@pytest.fixture(scope="module")
def fixtures(settings: Settings) -> Fixtures:
    return Fixtures(settings.work_dir)


def init_path(repository_id: str) -> str:
    return f"{REPOSITORIES}/{repository_id}/init"


def project_of(api: httpx.Client, project_id: str) -> dict[str, Any]:
    response = api.get(f"{PROJECTS}/{project_id}")
    assert response.status_code == HTTP_OK, response.text
    body: dict[str, Any] = response.json()
    return body


def repository_of(project: dict[str, Any], repository_id: str) -> dict[str, Any]:
    (repository,) = [r for r in project["repositories"] if r["id"] == repository_id]
    return repository


def run_of(project: dict[str, Any], run_id: str) -> dict[str, Any]:
    (run,) = [r for r in project["runs"] if r["id"] == run_id]
    return run


#: The park kinds `continue` answers (`application/rules/signals_table.py`'s own row).
CONTINUABLE = frozenset({"checkpoint", "protected_path", "plan_stale"})


def wait_until_terminal(api: httpx.Client, run_id: str) -> str:
    """Drive the Run to a terminal status, playing the Operator at its declared stop.

    Operator revision 2026-09-15: `repo-init@1` gained a `context` step and a
    `context-review` checkpoint (f79a2a1), so the Run now parks `needs_you` there by
    design; this driver sends `continue` the way the Operator would.

    Operator revision 2026-09-16: a park is read before it is answered — `continue` on a
    kind that does not admit it is a 409 by design (`signals_table`), and asserting 200
    on every `needs_you` aborted the module with the Run stranded on its queue slot.
    An un-continuable park fails naming the kind and reason; `cancel_run` cleans up.
    """
    deadline = time.monotonic() + RUN_TIMEOUT_SECONDS
    status = status_of(api, run_id)
    while status in ("queued", "running", "needs_you") and time.monotonic() < deadline:
        if status == "needs_you":
            alert = alert_of(api, run_id)
            # `None` while `needs_you` is the moment between a signal's own commit and
            # the walker moving the row — transitional, not a park to answer or fail on
            if alert is not None:
                kind = alert.get("park_kind")
                if kind not in CONTINUABLE:
                    pytest.fail(f"run {run_id} parked {kind}: {alert.get('reason')}")
                continued = api.post(f"/api/v1/runs/{run_id}/signals", json={"kind": "continue"})
                assert continued.status_code == HTTP_OK, continued.text
        time.sleep(POLL_INTERVAL_SECONDS)
        status = status_of(api, run_id)
    return status


def status_of(api: httpx.Client, run_id: str) -> str:
    response = api.get(f"/api/v1/runs/{run_id}")
    assert response.status_code == HTTP_OK, response.text
    return str(response.json()["status"])


def alert_of(api: httpx.Client, run_id: str) -> dict[str, Any] | None:
    """The parked Run's declared stop, from the detail read the Operator's screen makes."""
    response = api.get(f"/api/v1/runs/{run_id}/detail")
    assert response.status_code == HTTP_OK, response.text
    alert: dict[str, Any] | None = response.json()["alert"]
    return alert


def start_init(api: httpx.Client, repository_id: str) -> str:
    """POST the init, dispatching the seeded `fake` harness (Operator decision,
    2026-09-16): the e2e stack runs no real harness, and the endpoint's optional
    `harness` body exists for exactly this stack's situation."""
    created = api.post(init_path(repository_id), json={"harness": "fake"})
    assert created.status_code == HTTP_CREATED, created.text
    return str(created.json()["run"]["id"])


def cancel_run(api: httpx.Client, run_id: str) -> None:
    """Best-effort release of the Run's queue slot (AD-12); a terminal Run refuses with
    409 and that is fine — the slot is already free."""
    api.post(f"/api/v1/runs/{run_id}/signals", json={"kind": "cancel"})


@pytest.fixture(scope="module")
def initialised(api: httpx.Client, fixtures: Fixtures) -> Iterator[dict[str, Any]]:
    """A Repository with no method, initialised end to end through this story's own route.
    The `finally` cancel (Operator revision, 2026-09-16) releases the queue slot a failed
    drive would otherwise hold for the rest of the stack's life (AD-12)."""
    project_id = create_project(api)
    origin = fixtures.make()
    repository_id = create_repository(api, project_id, origin)
    clone_check(api, repository_id)
    checked_before = repository_of(project_of(api, project_id), repository_id)["clone_check"]["at"]

    run_id = start_init(api, repository_id)
    try:
        yield {
            "project_id": project_id,
            "repository_id": repository_id,
            "run_id": run_id,
            "status": wait_until_terminal(api, run_id),
            "checked_before": checked_before,
        }
    finally:
        cancel_run(api, run_id)


def test_the_run_reaches_done(initialised: dict[str, Any]) -> None:
    assert initialised["status"] == "done", initialised


def test_the_completion_hook_re_runs_the_clone_check(
    initialised: dict[str, Any], api: httpx.Client
) -> None:
    """The brief's own `[ASSUMPTION: a completion hook re-runs the clone check]`, proven by
    the check's own timestamp advancing with no `POST .../clone-check` call from this test.

    `bmad_version` itself stays `missing`: `repo-init@1` pushes `_bmad/` to `chore/bmad-init`
    only (AD-16), and the clone check reads `repository.default_branch` (FR-30's own words,
    AD-16's own "informational" on the Repository row) — `main` never changes until the
    Operator merges the compare link this Run's own row shows, which this vertical slice
    does not simulate (no PR is created; "a compare link", never a merge). Re-checking is
    still real work: a check the Operator merged mid-Run, or between this Run and their next
    visit, is picked up without them clicking *re-run check* themselves.
    """
    project = project_of(api, initialised["project_id"])
    repository = repository_of(project, initialised["repository_id"])

    assert repository["clone_check"]["at"] > initialised["checked_before"]
    assert repository["clone_check"]["bmad_version"] == "missing"


def test_the_row_shows_the_compare_link_and_the_run_reads_done(
    initialised: dict[str, Any], api: httpx.Client
) -> None:
    project = project_of(api, initialised["project_id"])
    run = run_of(project, initialised["run_id"])

    assert run["token"] == DONE
    assert run["template"] == "repo-init@1"
    # a local `file://` origin is not GitHub (`test_repo_init.py`'s own finding): `pr.link`
    # records no compare URL for it, so this Run's own list carries none either
    assert run["compare_urls"] == []


def test_a_second_init_while_the_first_is_still_going_is_refused(
    api: httpx.Client, fixtures: Fixtures
) -> None:
    project_id = create_project(api)
    origin = fixtures.make()
    repository_id = create_repository(api, project_id, origin)
    clone_check(api, repository_id)

    run_id = start_init(api, repository_id)
    try:
        second = api.post(init_path(repository_id))

        assert second.status_code == HTTP_CONFLICT, second.text
        assert run_id in second.json()["detail"]

        # let the Run finish so it releases the Repository's queue partition (AD-12) before
        # the module's other tests and its own teardown run
        wait_until_terminal(api, run_id)
    finally:
        cancel_run(api, run_id)


def test_a_failed_clone_check_refuses_initialisation(api: httpx.Client) -> None:
    project_id = create_project(api)
    repository_id = create_repository(
        api, project_id, f"https://github.com/example/unreachable-{uuid4().hex}.git"
    )
    clone_check_response = api.post(f"{REPOSITORIES}/{repository_id}/clone-check")
    assert clone_check_response.status_code == HTTP_OK, clone_check_response.text
    assert clone_check_response.json()["status"] == "failed"

    response = api.post(init_path(repository_id))

    assert response.status_code == HTTP_CONFLICT, response.text
    assert "clone check failed" in response.json()["detail"]


def test_an_unknown_repository_is_not_found(api: httpx.Client) -> None:
    response = api.post(init_path(str(uuid4())))

    assert response.status_code == HTTP_NOT_FOUND, response.text


def test_get_reads_the_repository_this_path_initialises(
    api: httpx.Client, fixtures: Fixtures
) -> None:
    project_id = create_project(api)
    origin = fixtures.make()
    repository_id = create_repository(api, project_id, origin)

    response = api.get(init_path(repository_id))

    assert response.status_code == HTTP_OK, response.text
    assert response.json()["id"] == repository_id
