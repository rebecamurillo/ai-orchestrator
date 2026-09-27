"""`repo-init@1` end to end: the epic's headline acceptance (SPEC CAP-8, FR-30, AD-16).

Everything the six git kinds decide is proven over fakes in the unit suite. What only the
running stack settles is that they are *real*: that the image carries a `git` and an `npx`
that can do this, that `GIT_ASKPASS` and the built environment do not get in the way of a
`file://` remote, that the base clone, the worktree, the install, the commit and the push
happen in that order on one Run, and that the branch and the commit the Operator was promised
actually exist on the origin afterwards.

**The origin is a local bare repository.** `tests/e2e/test_clone_check.py::Fixtures` already
makes one under `WORK_DIR/e2e-fixtures` and registers it by `file://`, in both topologies —
CI, where the backend runs on this machine, and `make up`, where only the named volumes are
shared. A second helper would be a second double, so this module imports that one and adds
only what it needs beyond it: reading the origin back after the Run.

**The Repository carries no `_bmad/`.** That is the case `repo-init` exists for, and AD-16
exempts a plan containing a `bmad.install` row from the pre-flight that would otherwise
require the method to be there already.

**`pr.link` records nothing here, and says so.** A `file://` origin is not GitHub, so the row
ends `done` with `no compare link for this host`. That the compare URL itself is built
correctly is asserted against a `github.com` URL in `tests/unit/test_pr_link_executor.py`,
where it can be checked without owning a GitHub repository.

**The Run stops once, on purpose.** `repo-init@1`'s `context` step dispatches
`bmad-project-context`, whose output is the repository's `AGENTS.md`, and the
`context-review` step after it is a `checkpoint`: the Operator reads the block before it is
committed. So this module does not wait for a Run that runs straight through — it waits for
the park, answers it with *Continue*, and only then waits for `done`. The dispatch itself is
the `fake` harness: what the real skill would write is a conversation, and what this gate is
for is the order of the rows, the stop, and the branch that exists afterwards.

This module leaves its Run terminal, so it holds neither its slot nor its Repository
partition afterwards (AD-12).
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest

from orchestrator.infrastructure.db import (
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    create_engine_from,
    create_session_factory,
)
from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import FIXTURE_DIRECTORY, REPO_ROOT, Fixtures
from tests.e2e.test_run_creation import (
    RUNS,
    clone_check,
    create_project,
    create_repository,
    project_id_of,
    run_payload,
)

HTTP_CREATED = 201
HTTP_OK = 200
TIMEOUT_SECONDS = 10.0

#: The shipped Template this module runs, and the branch it works on (AD-16). A Run never
#: works on the name the Template declares: it works on the first ordinal of it the origin
#: does not already hold (`templates/branches.py`), and this module's origin is made fresh,
#: so it is always the first.
TEMPLATE = "repo-init"
DECLARED_BRANCH = "chore/bmad-init"
INIT_BRANCH = f"{DECLARED_BRANCH}-1"
COMMIT_SUBJECT = "chore: initialise BMAD method (orchestrator)"

#: The rows `repo-init@1` plans, in order (`templates/repo-init.yaml` plus AD-7's row 1).
#: `setup` is the declared install row (Operator decision, 2026-09-27); this module's
#: repository declares no `install_command`, so it plans `skipped · no command`.
ROWS = (
    "plan",
    "checkout",
    "setup",
    "install",
    "context",
    "context-review",
    "commit",
    "push",
    "link",
)

#: The row the Run stops on, and what it stops with.
STOP_ROW = "context-review"
STOP_KIND = "checkpoint"
#: What the Run's status is while it waits there (AD-8's operator half).
NEEDS_YOU = "needs_you"

#: The harness this suite dispatches on. The `context` step runs `bmad-project-context`,
#: which is a conversation with an Operator; the scripted harness writes what its scenario
#: says and, with no scenario in this fixture, writes nothing and exits 0
#: (`infrastructure/harness/fake/scenario.py`). What is under test here is the plan, the
#: stop and the branch — not what the skill would have said.
SCRIPTED_HARNESS = "fake"

#: `bmad.install` fetches a package from the npm registry and writes a whole method into the
#: worktree; the Template gives it 30 minutes. This is the gate's own patience, not a claim
#: about how long it takes.
RUN_TIMEOUT_SECONDS = 900.0
POLL_INTERVAL_SECONDS = 2.0

#: What `pr.link` records for an origin that is not GitHub.
NO_LINK = "no compare link for this host"

#: The two lines `bmad.install` appends, so the commit after it never sees a skill folder.
IGNORED = (".claude/skills/bmad-*", ".agents/skills/bmad-*")

#: What is read back off the origin, as one script so it runs unchanged in either topology.
#: `$1` is the fixtures directory, `$2` the repository name, `$3` the branch.
READ_BACK = """
set -e
dir="$1"; name="$2"; branch="$3"
git --git-dir="$dir/$name.git" log -1 --format=%s "$branch"
echo "--- files ---"
git --git-dir="$dir/$name.git" ls-tree -r --name-only "$branch"
echo "--- gitignore ---"
git --git-dir="$dir/$name.git" show "$branch:.gitignore"
"""


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
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


@pytest.fixture(scope="module")
def test_mode(api: httpx.Client) -> None:
    """Fail by name when the stack is not in test mode, rather than timing out later.

    `repo-init@1` dispatches an agent since its `context` step landed, and the one harness
    this suite can run is the scripted one — the real skill is a conversation.
    """
    response = api.get("/api/v1/harnesses")
    assert response.status_code == HTTP_OK, response.text
    rows = {item["name"]: item for item in response.json()["items"]}
    assert SCRIPTED_HARNESS in rows, (
        f"the `{SCRIPTED_HARNESS}` harness is not seeded: this gate needs ORCH_TEST_MODE=1 "
        "on the stack (docker-compose.e2e.yml sets it; `make e2e` is the target that uses it)"
    )
    assert rows[SCRIPTED_HARNESS]["enabled"] is True, rows[SCRIPTED_HARNESS]


@pytest.fixture(scope="module")
def origin(api: httpx.Client, fixtures: Fixtures) -> str:
    """A bare repository with `main` and no `_bmad/` — what `repo-init` is for."""
    return fixtures.make()


def name_of(url: str) -> str:
    """The fixture's own name, back out of the URL `Fixtures.url` composed."""
    return url.rsplit("/", 1)[-1].removesuffix(".git")


def read_back(work_dir: Path, name: str) -> str:
    """Read the origin after the Run, on this host or inside the container — never neither."""
    arguments = [str(work_dir / FIXTURE_DIRECTORY), name, INIT_BRANCH]
    refusals = []
    routes = (
        ["sh", "-c", READ_BACK, "sh", *arguments],
        [
            *("docker", "compose", "exec", "-T", "backend-api"),
            *("sh", "-c", READ_BACK, "sh", *arguments),
        ],
    )
    for command in routes:
        try:
            done = subprocess.run(  # fixed argv, no shell
                command, cwd=REPO_ROOT, capture_output=True, text=True, check=False
            )
        except OSError as error:
            refusals.append(str(error))
            continue
        if done.returncode == 0:
            return done.stdout
        refusals.append((done.stderr or done.stdout).strip())
    pytest.fail(f"no route to read the origin back: {' | '.join(refusals)}")


@pytest.fixture(scope="module")
def initialised(
    api: httpx.Client, origin: str, settings: Settings, test_mode: None
) -> dict[str, Any]:
    """The whole story in one fixture: a Repository with no method, initialised."""
    project_id = create_project(api)
    repository_id = create_repository(api, project_id, origin)
    clone_check(api, repository_id)
    payload = run_payload(
        TEMPLATE,
        repository_id,
        project_id=project_id_of(api, repository_id),
        harness=SCRIPTED_HARNESS,
    )
    created = api.post(RUNS, json=payload)
    assert created.status_code == HTTP_CREATED, created.text
    run_id = str(created.json()["run"]["id"])
    parked = wait_until_terminal(api, run_id)
    stop = park_of(api, run_id) if parked == NEEDS_YOU else None
    return {
        "id": run_id,
        "parked": parked,
        "stop": stop,
        "status": continued(api, run_id) if parked == NEEDS_YOU else parked,
        "origin": origin,
    }


def park_of(client: httpx.Client, run_id: str) -> dict[str, Any]:
    """What the Run says it is waiting for, as the Operator's screen reads it.

    Operator revision 2026-09-16: reads `GET /runs/{id}/detail` — `alert` and `steps`
    are `RunDetailOut`'s fields; the summary route this read before has neither, so
    every assertion on the captured stop raised `KeyError` instead of asserting."""
    response = client.get(f"{RUNS}/{run_id}/detail")
    assert response.status_code == HTTP_OK, response.text
    return dict(response.json())


def continued(client: httpx.Client, run_id: str) -> str:
    """Answer the one declared stop, then wait for the Run to finish (AD-13)."""
    response = client.post(f"{RUNS}/{run_id}/signals", json={"kind": "continue"})
    assert response.status_code in (HTTP_OK, HTTP_CREATED), response.text
    return wait_until_terminal(client, run_id)


def wait_until_terminal(client: httpx.Client, run_id: str) -> str:
    """Poll until the Run leaves `queued`/`running`, or fail naming the deadline."""
    deadline = time.monotonic() + RUN_TIMEOUT_SECONDS
    status = status_of(client, run_id)
    while status in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        status = status_of(client, run_id)
    return status


def status_of(client: httpx.Client, run_id: str) -> str:
    response = client.get(f"{RUNS}/{run_id}")
    assert response.status_code == HTTP_OK, response.text
    return str(response.json()["status"])


def rows_of(sessions: Any, run_id: str) -> list[Any]:
    with sessions() as session:
        return SQLAlchemyStepRunRepository(session).list_for_run(UUID(run_id))


def run_of(sessions: Any, run_id: str) -> Any:
    with sessions() as session:
        return SQLAlchemyRunRepository(session).get(UUID(run_id))


def test_the_run_stops_for_the_operator_at_the_context_review(
    initialised: dict[str, Any],
) -> None:
    """The declared stop, before anything is committed: the Operator reads the block the
    `context` step wrote and answers it. A Run that never stopped would have committed an
    `AGENTS.md` nobody looked at.

    Operator revision 2026-09-15: asserted on the parked snapshot the fixture captured,
    not on the final row — `signal_run` clears `park_*` when the Operator continues
    (AD-8), so after the fixture's own `continue` the database row cannot carry the stop
    this test is about; as written before this date it could never pass."""
    assert initialised["parked"] == NEEDS_YOU, initialised

    stop = initialised["stop"]

    assert stop is not None
    assert stop["alert"] is not None, stop
    assert stop["alert"]["park_kind"] == STOP_KIND
    review = next(step for step in stop["steps"] if step["path"] == STOP_ROW)
    assert review["status"] == "checkpoint"


def test_the_context_step_wrote_its_agents_file_without_parking_on_it(
    initialised: dict[str, Any], sessions: Any
) -> None:
    """AD-17 protects every `AGENTS.md`, and `repo-init@1` declares this one under `writes`
    — so the dispatch that was sent to write it is not a dispatch that went where nobody
    sent it. Without the declaration the Run would park `protected_path` on the `context`
    row instead of reaching its own checkpoint."""
    context = next(row for row in rows_of(sessions, initialised["id"]) if row.path == "context")

    assert context.status == "done"


def test_the_run_reaches_done(initialised: dict[str, Any], sessions: Any) -> None:
    """The one assertion the whole epic is for. A park names its own reason."""
    if initialised["status"] != "done":
        run = run_of(sessions, initialised["id"])
        pytest.fail(
            f"repo-init ended {initialised['status']}: "
            f"{run.park_kind} at {run.park_path} — {run.park_reason}"
        )


def test_every_planned_row_ran_in_order(initialised: dict[str, Any], sessions: Any) -> None:
    rows = rows_of(sessions, initialised["id"])

    assert [row.path for row in rows] == list(ROWS)
    expected = ["skipped" if row == "setup" else "done" for row in ROWS]
    assert [row.status for row in rows] == expected


def test_the_run_records_the_worktree_it_created_and_pushed(
    initialised: dict[str, Any], sessions: Any
) -> None:
    """AD-14: `git.worktree` appends the entry, `git.push` marks it `pushed`."""
    run = run_of(sessions, initialised["id"])

    assert run is not None
    assert len(run.worktrees) == 1
    entry = run.worktrees[0]
    assert entry.branch == INIT_BRANCH
    assert entry.created_branch is True
    assert entry.pushed is True
    assert run.worktree_path == entry.path


def test_a_non_github_origin_records_no_compare_link_and_says_so(
    initialised: dict[str, Any], sessions: Any
) -> None:
    run = run_of(sessions, initialised["id"])
    link = next(row for row in rows_of(sessions, initialised["id"]) if row.path == "link")

    assert run is not None
    assert run.compare_urls == ()
    assert link.reason == NO_LINK


def test_the_origin_holds_the_branch_with_the_method_committed(
    initialised: dict[str, Any], settings: Settings
) -> None:
    """FR-30's whole promise, read off the remote rather than off the Run."""
    output = read_back(settings.work_dir, name_of(initialised["origin"]))

    subject, _, rest = output.partition("\n--- files ---\n")
    files, _, gitignore = rest.partition("\n--- gitignore ---\n")
    committed = files.split()

    assert subject.strip() == COMMIT_SUBJECT
    assert any(path.startswith("_bmad/") for path in committed), committed
    assert all(line in gitignore for line in IGNORED), gitignore


def test_no_skill_folder_was_committed(initialised: dict[str, Any], settings: Settings) -> None:
    """AD-16: skill folders are never committed; the two ignore lines are what keeps them out."""
    output = read_back(settings.work_dir, name_of(initialised["origin"]))
    _, _, rest = output.partition("\n--- files ---\n")
    files, _, _gitignore = rest.partition("\n--- gitignore ---\n")

    committed = files.split()
    assert not [path for path in committed if path.startswith(".claude/skills/bmad-")]
    assert not [path for path in committed if path.startswith(".agents/skills/bmad-")]
