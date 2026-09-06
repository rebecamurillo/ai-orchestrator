"""The durable engine, walking a real Run in the real image (SPEC CAP-6, AD-6, AD-12).

Everything the walker decides is proven over fakes in the unit suite. What only the running
stack settles is that there *is* an engine: that the image carries the library, that
`DBOS.launch()` ran inside the start-up step, that the queue exists, that `POST /runs`
enqueues onto it, and that the workflow this process registered picks the Run up and drives
it through the same writers a unit test drives by hand.

**This module's own Template is one `checkpoint` step, deliberately.** 4.7 registered
`plan.check`, `shell` and `checkpoint`; a Template built only from `shell` (as
`test_run_creation.py::LEAF` is) now runs straight to `done`, which is correct — the whole
point of landing those executors — but would leave nothing here parked to test AD-12
against. `checkpoint` always stops for the Operator on its first execution
(`application/steps/checkpoint.py`), so `CHECKPOINT_TEMPLATE` is what keeps this module
able to prove the property its own tests are about: a Run in `needs_you` holds its slot and
its Repository partition, and a second Run on the same Repository stays `queued` behind it.

**This module runs first among the Run-creating suites, and it leaves a Run parked.** The
Run reaches `needs_you` on its `pause` row, which holds its slot and its Repository
partition for the rest of the stack's life (AD-12). There is no signals endpoint until 4.9,
so nothing can release it: `make e2e` builds and destroys a stack of its own for exactly
this reason. Running the gate twice against one stack is not possible while a Run cannot be
cancelled, and that is recorded as a deferred item on this story rather than worked around
here.

*(One-off note, story 4.7: the operator authorised editing this file on 2026-09-06 to
replace `LEAF` with `CHECKPOINT_TEMPLATE` for exactly this fixture — the root cause was this
test's own precondition depending on an executor being missing, which stopped being true the
moment `plan.check` and `shell` were registered. That authorisation is about this file, this
once; it is not a standing rule and no later story may cite it on its own to edit an anchor.)*
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from orchestrator.infrastructure.db import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyGateRecordRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
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
    project_id_of,
    run_payload,
)

HTTP_CREATED = 201
HTTP_OK = 200

#: How long the walker is given to pick a Run up and stop it. The queue polls on its own
#: interval, so this is a deadline, not an expectation.
WALK_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.5

#: The statuses a walked Run can be in: anything but the one it was created in.
QUEUED = "queued"
#: What a Run parked on `checkpoint` reaches (AD-13), and the `park_kind` it reaches it with.
NEEDS_YOU = "needs_you"
CHECKPOINT_PARK_KIND = "checkpoint"

#: This module's own Template — one `checkpoint` step — so its first Run genuinely parks
#: rather than running straight to `done` the way `test_run_creation.py::LEAF` now does
#: once `shell` is registered (4.7). See the module docstring.
CHECKPOINT_TEMPLATE = (
    "name: {name}\nversion: 1\ndescription: e2e walker checkpoint\n"
    "inputs:\n"
    "  project:     {{ type: project,    required: true }}\n"
    "  repository:  {{ type: repository, required: true }}\n"
    "  base_branch: {{ type: string,     required: true }}\n"
    "steps:\n"
    "  - id: pause\n"
    "    uses: checkpoint\n"
    "    gate: human\n"
)


def save_checkpoint_template(client: httpx.Client, name: str) -> dict[str, object]:
    response = client.post(
        f"{TEMPLATES}/{name}/versions", json={"yaml": CHECKPOINT_TEMPLATE.format(name=name)}
    )
    assert response.status_code == HTTP_CREATED, response.text
    body: dict[str, object] = response.json()
    return body


#: The suite's own client timeout, matching `tests/e2e/conftest.py`.
TIMEOUT_SECONDS = 10.0


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    """A module-scoped client: the Run this module walks is shared by every assertion."""
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
def repository_id(api: httpx.Client, fixtures: Fixtures, settings: Settings) -> str:
    """One Project and one real bare repository, shared by both Runs this module creates."""
    project_id = create_project(api)
    url = fixtures.make(manifest_stating(settings.bmad_version))
    repository = create_repository(api, project_id, url)
    clone_check(api, repository)
    return repository


def start_run(client: httpx.Client, repository: str) -> dict[str, Any]:
    name = f"e2e-walker-{uuid4().hex}"
    save_checkpoint_template(client, name)
    payload = run_payload(name, repository, project_id=project_id_of(client, repository))
    response = client.post(RUNS, json=payload)
    assert response.status_code == HTTP_CREATED, response.text
    body: dict[str, Any] = response.json()
    return body


def status_of(client: httpx.Client, run_id: str) -> str:
    response = client.get(f"{RUNS}/{run_id}")
    assert response.status_code == HTTP_OK, response.text
    return str(response.json()["status"])


def wait_until_walked(client: httpx.Client, run_id: str) -> str:
    """Poll until the walker has moved the Run off `queued`, or fail naming the deadline."""
    deadline = time.monotonic() + WALK_TIMEOUT_SECONDS
    status = status_of(client, run_id)
    while status == "queued" and time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        status = status_of(client, run_id)
    if status == "queued":
        pytest.fail(
            f"run {run_id} was still queued after {WALK_TIMEOUT_SECONDS:.0f}s: "
            "the durable engine did not pick it up"
        )
    return status


@pytest.fixture(scope="module")
def walked(api: httpx.Client, repository_id: str) -> dict[str, Any]:
    """The first Run: created, enqueued, walked past `plan.check`, and parked on `pause`."""
    created = start_run(api, repository_id)
    run_id = str(created["run"]["id"])
    return {"id": run_id, "status": wait_until_walked(api, run_id), "body": created}


def test_the_engine_picks_the_run_up_and_walks_it(walked: dict[str, Any]) -> None:
    """The whole chain in one assertion: launched engine, queue, workflow, writers."""
    assert walked["status"] == NEEDS_YOU


def test_the_run_carries_the_workflow_the_adapter_started_it_as(
    walked: dict[str, Any], sessions: Any
) -> None:
    """AD-6: `engine_ref` is opaque JSON, and the workflow id is the Run's own id."""
    with sessions() as session:
        run = SQLAlchemyRunRepository(session).get(UUID(walked["id"]))

    assert run is not None
    assert run.engine_ref == {"workflow_id": walked["id"]}


def test_a_run_that_stopped_says_where_and_why(walked: dict[str, Any], sessions: Any) -> None:
    """The three park fields are written together (AD-8), naming the `pause` row and the
    `checkpoint` kind that stopped it."""
    with sessions() as session:
        run = SQLAlchemyRunRepository(session).get(UUID(walked["id"]))

    assert run is not None
    assert run.park_kind == CHECKPOINT_PARK_KIND
    assert run.park_path == "pause"
    assert run.park_reason


def test_the_first_row_ran_once_and_recorded_one_attempt(
    walked: dict[str, Any], sessions: Any
) -> None:
    """Exactly one Attempt: the walker's step ran once, which is what durability means."""
    with sessions() as session:
        rows = SQLAlchemyStepRunRepository(session).list_for_run(UUID(walked["id"]))
        attempts = SQLAlchemyAttemptRepository(session).list_for_row(rows[0].id)

    assert [attempt.n for attempt in attempts] == [1]
    assert attempts[0].ended_at is not None
    assert attempts[0].engine_ref["workflow_id"] == walked["id"]
    assert attempts[0].status == rows[0].status


def test_no_row_was_reached_out_of_order(walked: dict[str, Any], sessions: Any) -> None:
    """The walker executes rows in `seq` order: once one is untouched, so is every later one."""
    with sessions() as session:
        rows = SQLAlchemyStepRunRepository(session).list_for_run(UUID(walked["id"]))

    statuses = [row.status for row in rows]
    untouched = [index for index, status in enumerate(statuses) if status == "planned"]
    assert untouched == list(range(len(statuses) - len(untouched), len(statuses)))


def test_the_run_opens_its_gate_record_with_the_start(
    walked: dict[str, Any], sessions: Any
) -> None:
    """One `start` line, written once, by the writer the walker's first step called (AD-8)."""
    with sessions() as session:
        records = SQLAlchemyGateRecordRepository(session).list_for_run(UUID(walked["id"]))

    events = [record.event for record in records]
    assert events[0] == "start"
    assert events.count("start") == 1
    assert all(record.at.tzinfo is not None for record in records)


def test_a_second_run_on_the_same_repository_does_not_run_while_the_first_holds_it(
    api: httpx.Client, repository_id: str, walked: dict[str, Any]
) -> None:
    """AD-12: the Repository is the queue's partition, and a parked Run keeps it."""
    second = start_run(api, repository_id)
    run_id = str(second["run"]["id"])

    assert second["starts_now"] is False
    time.sleep(POLL_INTERVAL_SECONDS * 4)
    assert status_of(api, run_id) == QUEUED
