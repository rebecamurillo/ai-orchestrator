"""`POST /api/v1/runs/{id}/signals` against the real engine and real git (SPEC CAP-9,
FR-20, AD-13).

`handle_signal`'s rules are `test_handle_signal.py`'s own coverage over fakes; what only the
running stack settles is the brief's own e2e acceptance criterion — a Run parked on a real
`checkpoint` row really resumes and the walker really carries on past it — plus, because
`cancel` is destructive by design and this is the first caller of `Git.remove_worktree` /
`Git.delete_branch` outside a unit test, that a cancelled Run's worktree and branch are
really gone from the base clone `git.worktree` made them in.

**This module is what makes the gate twice-runnable again.** `test_engine_walker.py`'s own
docstring records that its `checkpoint` Run holds one of `MAX_ACTIVE_RUNS`'s two global
slots for the rest of the stack's life, because nothing before this story could release it.
The last test below cancels every `needs_you` Run the stack still holds — that module's
fixture included — so a second `pytest tests/e2e` against the same stack starts with every
slot free, the way `make e2e-api`'s own module docstring already promises this suite should.
Every Run this module creates itself also ends terminal by the end of its own test: nothing
here adds a new leak while closing the old one.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from orchestrator.infrastructure.db import (
    SQLAlchemyRunRepository,
    create_engine_from,
    create_session_factory,
)
from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import Fixtures, manifest_stating
from tests.e2e.test_run_creation import (
    RUNS,
    TEMPLATES,
    clone_check,
    create_project,
    create_repository,
    run_payload,
)

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_CONFLICT = 409

WALK_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.5

NEEDS_YOU = "needs_you"
DONE = "done"
CANCELLED = "cancelled"

REPO_ROOT = Path(__file__).resolve().parents[3]

#: `checkout` (a real, never-pushed branch) → `pause` (a real `checkpoint`) → `after` (a
#: `shell` no-op) — one Template two of this module's scenarios share. `continue` on
#: `pause` proves the brief's own e2e AC; `cancel` on `pause` proves the real git cleanup.
TWO_STEP_TEMPLATE = (
    "name: {name}\nversion: 1\ndescription: e2e signals\n"
    "inputs:\n"
    "  project:     {{ type: project,    required: true }}\n"
    "  repository:  {{ type: repository, required: true }}\n"
    "  base_branch: {{ type: string,     required: true }}\n"
    "steps:\n"
    "  - id: checkout\n"
    "    uses: git.worktree\n"
    "    with: {{ base: '{{{{base_branch}}}}', branch: '{branch}' }}\n"
    "    gate: deterministic\n"
    "  - id: pause\n"
    "    uses: checkpoint\n"
    "    gate: human\n"
    "  - id: after\n"
    "    uses: shell\n"
    "    with: {{ command: 'true' }}\n"
    "    gate: deterministic\n"
)

#: Runs a check against the base clone in either topology — `test_clone_check.py::Fixtures`
#: does the identical two-route thing for making a fixture; this checks one instead.
CHECK_CLEANED_UP = """
set -e
base="$1"; path="$2"; branch="$3"
if [ -e "$path" ]; then echo "worktree still present: $path"; exit 1; fi
if git -C "$base" branch --list "$branch" | grep -q .; then
  echo "branch still present: $branch"; exit 1
fi
"""


def save_template(client: httpx.Client, name: str, branch: str) -> None:
    yaml = TWO_STEP_TEMPLATE.format(name=name, branch=branch)
    response = client.post(f"{TEMPLATES}/{name}/versions", json={"yaml": yaml})
    assert response.status_code == HTTP_CREATED, response.text


def status_of(client: httpx.Client, run_id: str) -> str:
    response = client.get(f"{RUNS}/{run_id}")
    assert response.status_code == HTTP_OK, response.text
    return str(response.json()["status"])


def wait_for(client: httpx.Client, run_id: str, targets: set[str]) -> str:
    deadline = time.monotonic() + WALK_TIMEOUT_SECONDS
    status = status_of(client, run_id)
    while status not in targets and time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        status = status_of(client, run_id)
    if status not in targets:
        pytest.fail(
            f"run {run_id} did not reach {targets} within {WALK_TIMEOUT_SECONDS:.0f}s"
            f" (last seen: {status})"
        )
    return status


def signal(client: httpx.Client, run_id: str, kind: str, **payload: object) -> httpx.Response:
    return client.post(f"{RUNS}/{run_id}/signals", json={"kind": kind, "payload": payload})


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


@pytest.fixture(scope="module")
def sessions(settings: Settings) -> Iterator[Any]:
    engine = create_engine_from(settings)
    try:
        yield create_session_factory(engine)
    finally:
        engine.dispose()


def new_repository(api: httpx.Client, fixtures: Fixtures, settings: Settings) -> tuple[str, str]:
    """A fresh Project and a fresh real bare repository — one pair per scenario, so this
    module's own two Runs never contend for the same Repository partition (AD-12)."""
    project_id = create_project(api)
    url = fixtures.make(manifest_stating(settings.bmad_version))
    repository_id = create_repository(api, project_id, url)
    clone_check(api, repository_id)
    return project_id, repository_id


def start_run(api: httpx.Client, repository_id: str, project_id: str, branch: str) -> str:
    name = f"e2e-signals-{uuid4().hex}"
    save_template(api, name, branch)
    payload = run_payload(name, repository_id, project_id=project_id)
    response = api.post(RUNS, json=payload)
    assert response.status_code == HTTP_CREATED, response.text
    return str(response.json()["run"]["id"])


def run_check(args: list[str]) -> bool:
    """The check script, on this host or inside the container — whichever one can see the
    work directory `git.worktree` wrote under (`Fixtures._run`'s own two-route shape)."""
    in_container = ["docker", "compose", "exec", "-T", "backend-api"]
    for command in (
        ["sh", "-c", CHECK_CLEANED_UP, "sh", *args],
        [*in_container, "sh", "-c", CHECK_CLEANED_UP, "sh", *args],
    ):
        try:
            completed = subprocess.run(
                command, cwd=REPO_ROOT, capture_output=True, text=True, check=False
            )
        except OSError:
            continue
        if completed.returncode == 0:
            return True
    return False


# ── continue on a checkpoint row: the brief's own e2e AC ────────────────────────────────


def test_continue_on_a_checkpoint_row_lets_the_walker_finish_the_run(
    api: httpx.Client, fixtures: Fixtures, settings: Settings
) -> None:
    project_id, repository_id = new_repository(api, fixtures, settings)
    run_id = start_run(api, repository_id, project_id, "e2e-signals-continue")
    wait_for(api, run_id, {NEEDS_YOU})

    response = signal(api, run_id, "continue")

    assert response.status_code == HTTP_OK, response.text
    assert response.json()["status"] == "running"
    assert wait_for(api, run_id, {DONE}) == DONE


# ── cancel: kill, remove the worktree, delete the never-pushed branch ───────────────────


def test_cancel_removes_the_worktree_and_deletes_the_unpushed_branch(
    api: httpx.Client, fixtures: Fixtures, settings: Settings, sessions: Any
) -> None:
    project_id, repository_id = new_repository(api, fixtures, settings)
    branch = "e2e-signals-cancel"
    run_id = start_run(api, repository_id, project_id, branch)
    wait_for(api, run_id, {NEEDS_YOU})

    response = signal(api, run_id, "cancel", confirm=True)

    assert response.status_code == HTTP_OK, response.text
    assert response.json()["status"] == "cancelled"
    with sessions() as session:
        run = SQLAlchemyRunRepository(session).get(UUID(run_id))
    assert run is not None
    (worktree,) = run.worktrees
    assert worktree.branch == branch
    assert worktree.created_branch is True
    assert worktree.pushed is False
    base = str(Path(worktree.path).parent.parent / "base")
    assert run_check([base, worktree.path, branch]), (
        f"worktree/branch not cleaned up: base={base} path={worktree.path} branch={branch}"
    )


def test_a_cancelled_run_refuses_a_second_signal(
    api: httpx.Client, fixtures: Fixtures, settings: Settings
) -> None:
    project_id, repository_id = new_repository(api, fixtures, settings)
    run_id = start_run(api, repository_id, project_id, "e2e-signals-double-cancel")
    wait_for(api, run_id, {NEEDS_YOU})
    assert signal(api, run_id, "cancel", confirm=True).status_code == HTTP_OK

    response = signal(api, run_id, "retry")

    assert response.status_code == HTTP_CONFLICT, response.text


#: How many sweeps to cancel-and-recheck, and how long to let the queue react between them.
#: `test_engine_walker.py` leaves *two* Runs behind a Repository partition — the one it
#: walks to `needs_you`, and a second it deliberately leaves `queued` behind it to prove
#: AD-12 — so releasing the first is what lets the durable engine dequeue the second, which
#: then walks to its *own* `needs_you` a moment later. One pass is not enough; this converges.
SWEEP_ROUNDS = 5
SWEEP_SETTLE_SECONDS = 2.0


def needs_you_run_ids(api: httpx.Client) -> list[str]:
    response = api.get(RUNS)
    assert response.status_code == HTTP_OK, response.text
    return [run["id"] for run in response.json()["items"] if run["status"] == NEEDS_YOU]


# ── twice-runnable: release every Run this stack is still holding for the Operator ──────


def test_every_needs_you_run_this_stack_holds_can_be_released(api: httpx.Client) -> None:
    """Run last in this module (definition order, not alphabetical): by now every Run this
    module itself parked has already been continued or cancelled above, so this only ever
    reaches Runs an *earlier* module left behind — `test_engine_walker.py`'s own `checkpoint`
    fixture, most notably. Cancelling one frees a Repository partition (AD-12), which can let
    a Run that module left `queued` behind it advance to a park of its own a moment later —
    see `SWEEP_ROUNDS` — so this sweeps until a round finds nothing left to release. Freeing
    every slot here is what lets a second `pytest tests/e2e` against this same stack pick
    every Run up in turn, the way `make e2e-api`'s own module docstring says this suite must.
    """
    for _ in range(SWEEP_ROUNDS):
        parked = needs_you_run_ids(api)
        if not parked:
            return
        for run_id in parked:
            result = signal(api, run_id, "cancel", confirm=True)
            assert result.status_code == HTTP_OK, result.text
            assert result.json()["status"] == CANCELLED
        time.sleep(SWEEP_SETTLE_SECONDS)

    assert needs_you_run_ids(api) == []
