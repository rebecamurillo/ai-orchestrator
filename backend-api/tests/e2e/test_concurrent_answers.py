"""Two Run page answers naming one stop, sent at once: one 200, one 409, one `answer` record
(story 4-1, AD-8, AD-24; settles 1-1's deferred race).

`signal_run` reads the Run under its row lock, and an answer leaves `park_seq` as it was, so
the stop's identity alone cannot tell the two apart: whichever commits first moves the Run to
`running`, and the other is refused by the signal table under the lock — or, if it arrives
after the first has committed, by the router's own read ahead of it. Either way only one
answer is recorded, and only that one wakes the walker. Only the running stack has the real
row lock, which is why this lives here and not over the fakes.

Needs `ORCH_TEST_MODE=1` on the stack (`docker-compose.e2e.yml` sets it, `make e2e` uses it).
The Run is cancelled at the end so it holds neither a global slot nor its Repository's
partition (AD-12).
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.helpers.gates_fixture import GatesFixture
from tests.e2e.helpers.templates import save_epic_pair
from tests.e2e.test_answer_signal import detail_of, wait_for_park
from tests.e2e.test_run_creation import PROJECTS, RUNS, clone_check, create_project

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_CONFLICT = 409
TIMEOUT_SECONDS = 30.0

SPEC_FOLDER = "specs/gates"
QUALITY_GATE = "sh check.sh"
DECLARED_BRANCH = "epics/gates-race"

ANSWERS = ("Post to the project's channel only", "Post to every channel")


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture(scope="module")
def bmad_version() -> str:
    value = os.environ.get("BMAD_VERSION")
    if not value:
        pytest.fail(
            "BMAD_VERSION is not set: the gates fixture's `_bmad/` manifest has to state the "
            "version this instance pins (`make e2e` exports it from .env.e2e)"
        )
    return value


@pytest.fixture(scope="module")
def gates(settings: Settings, bmad_version: str) -> GatesFixture:
    return GatesFixture(settings.work_dir, bmad_version)


@pytest.fixture(scope="module")
def test_mode(api: httpx.Client) -> None:
    response = api.get("/api/v1/harnesses")
    assert response.status_code == HTTP_OK, response.text
    rows = {item["name"]: item for item in response.json()["items"]}
    assert "fake" in rows, (
        "the `fake` harness is not seeded: this gate needs ORCH_TEST_MODE=1 on the stack "
        "(docker-compose.e2e.yml sets it; `make e2e` is the target that uses it)"
    )
    assert rows["fake"]["enabled"] is True, rows["fake"]


@pytest.fixture(scope="module")
def parked(api: httpx.Client, gates: GatesFixture, test_mode: None) -> Iterator[dict[str, Any]]:
    """A Run on the gates fixture, walked until it parks `blocked` on story 1."""
    project_id = create_project(api)
    created = api.post(
        f"{PROJECTS}/{project_id}/repositories",
        json={
            "url": gates.make(),
            "default_branch": "main",
            "quality_gate_command": QUALITY_GATE,
            "unit_test_command": QUALITY_GATE,
        },
    )
    assert created.status_code == HTTP_CREATED, created.text
    repository_id = str(created.json()["id"])
    clone_check(api, repository_id)

    template_name, _ = save_epic_pair(api, "e2e-gates-race")

    started = api.post(
        RUNS,
        json={
            "template_name": template_name,
            "template_version": 1,
            "project_id": project_id,
            "repository_id": repository_id,
            "base_branch": "main",
            "budget_usd": "5",
            "harness": "fake",
            "inputs": {"spec_folder": SPEC_FOLDER, "branch": f"{DECLARED_BRANCH}-{uuid4().hex}"},
        },
    )
    assert started.status_code == HTTP_CREATED, started.text
    run_id = str(started.json()["run"]["id"])
    try:
        yield {"id": run_id, "detail": wait_for_park(api, run_id)}
    finally:
        api.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel"})


@pytest.fixture(scope="module")
def raced(stack: str, bearer: dict[str, str], parked: dict[str, Any]) -> list[httpx.Response]:
    """Both answers, released together from two clients, each naming the parked stop."""
    stop = parked["detail"]["run"]["park_seq"]
    start = threading.Barrier(len(ANSWERS))
    responses: dict[int, httpx.Response] = {}

    def answer(index: int) -> None:
        with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
            start.wait()
            responses[index] = client.post(
                f"{RUNS}/{parked['id']}/signals",
                json={"kind": "answer", "payload": {"text": ANSWERS[index]}, "stop": stop},
            )

    threads = [threading.Thread(target=answer, args=(i,)) for i in range(len(ANSWERS))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(TIMEOUT_SECONDS * 2)
    assert len(responses) == len(ANSWERS), "an answer request never returned"
    return [responses[i] for i in range(len(ANSWERS))]


def test_one_answer_is_applied_and_the_other_refused(raced: list[httpx.Response]) -> None:
    codes = sorted(response.status_code for response in raced)

    assert codes == [HTTP_OK, HTTP_CONFLICT], [response.text for response in raced]


def test_the_gate_record_holds_exactly_the_winning_answer(
    api: httpx.Client, parked: dict[str, Any], raced: list[httpx.Response]
) -> None:
    (winner,) = [i for i, response in enumerate(raced) if response.status_code == HTTP_OK]

    records = detail_of(api, parked["id"])["gate_record"]
    answers = [entry for entry in records if entry["event"] == "answer"]

    assert len(answers) == 1, answers
    assert answers[0]["text"] == ANSWERS[winner]
    assert answers[0]["actor"] == "operator"
