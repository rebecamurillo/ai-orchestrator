"""The interactive lane through the use cases (epic 3 story 2, AC2, AC3, AC6 router half)."""

from __future__ import annotations

import pytest

from orchestrator.api.providers import queue_ports
from orchestrator.application.use_cases import create_run as create_run_module
from orchestrator.application.use_cases.create_run import CreateRunRequest
from orchestrator.application.use_cases.dependency_sweep import sweep_dependency_waiting
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.application.use_cases.writers import enqueue_dependents
from orchestrator.domain.ports.engine import QueueEntry
from tests.unit.application import test_dependency_continue_signal as continue_module
from tests.unit.application import test_dependency_resolution as resolution
from tests.unit.application import test_start_signal as start_module
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_create_run_partition import BUDGET, Harness
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.test_queue_router import NOW, QUEUE, Api, a_run


def request() -> CreateRunRequest:
    return CreateRunRequest(
        template_name="repo-init",
        template_version=1,
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        base_branch=fixtures.BASE_BRANCH,
        budget_usd=BUDGET,
    )


def enqueue_lanes(engine: FakeWorkflowEngine) -> list[str]:
    return [args[2] for name, args in engine.calls if name == "enqueue"]  # type: ignore[index]


# ── AC2 ──────────────────────────────────────────────────────────────────────


def test_an_ordinary_template_creates_a_walk_run() -> None:
    harness = Harness()

    result = harness.create(request())

    run = result.run  # type: ignore[attr-defined]
    key = f"{fixtures.REPOSITORY.id}:{fixtures.INIT_BRANCH}"
    assert run.lane == "walk"
    assert harness.runs.get(run.id).lane == "walk"  # type: ignore[union-attr]
    assert harness.engine.calls == [("enqueue", (run.id, key, "walk"))]


def test_an_interactive_template_without_a_conversation_row_creates_a_walk_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = Harness()
    key = ("repo-init", 1)
    stored = harness.templates.versions[key]
    harness.templates.versions[key] = stored.model_copy(
        update={"yaml": stored.yaml.replace("version: 1\n", "version: 1\ntype: interactive\n", 1)}
    )
    seen: list[tuple[str, frozenset[str]]] = []
    real_lane_of = create_run_module.lane_of

    def spy(template_type: str, row_kinds: set[str]) -> str:
        seen.append((template_type, frozenset(row_kinds)))
        return real_lane_of(template_type, row_kinds)  # type: ignore[arg-type]

    monkeypatch.setattr(create_run_module, "lane_of", spy)

    result = harness.create(request())

    run = result.run  # type: ignore[attr-defined]
    branch_key = f"{fixtures.REPOSITORY.id}:{fixtures.INIT_BRANCH}"
    assert [template_type for template_type, _ in seen] == ["interactive"]
    assert "conversation" not in seen[0][1]
    assert run.lane == "walk"
    assert harness.runs.get(run.id).lane == "walk"  # type: ignore[union-attr]
    assert harness.engine.calls == [("enqueue", (run.id, branch_key, "walk"))]


def test_a_lane_rule_answer_of_interactive_is_stored_and_enqueued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(create_run_module, "lane_of", lambda *_: "interactive")
    harness = Harness()

    result = harness.create(request())

    run = result.run  # type: ignore[attr-defined]
    assert run.lane == "interactive"
    assert harness.runs.get(run.id).lane == "interactive"  # type: ignore[union-attr]
    assert enqueue_lanes(harness.engine) == ["interactive"]


# ── AC3 ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("lane", ["interactive", "walk"])
def test_the_start_signal_enqueues_on_the_runs_lane(lane: str) -> None:
    harness = start_module.StartHarness(git=fixtures.repo_init_git())
    saved = start_module.a_saved_run().model_copy(update={"lane": lane})

    harness.start(saved)

    assert enqueue_lanes(harness.engine) == [lane]


@pytest.mark.parametrize("lane", ["interactive", "walk"])
def test_the_dependency_continue_enqueues_on_the_runs_lane(lane: str) -> None:
    run = continue_module.a_dependency_parked_run(lane=lane)
    ports, engine, _ = continue_module.make_signal_ports(run)

    signal_run(ports, run.id, continue_module.CONTINUE)

    assert enqueue_lanes(engine) == [lane]


@pytest.mark.parametrize("lane", ["interactive", "walk"])
def test_a_resolved_dependent_is_enqueued_on_its_lane(lane: str) -> None:
    engine = FakeWorkflowEngine()
    predecessor = resolution.a_run("done")
    dependent = resolution.a_run("queued", after_run_ids=(predecessor.id,), lane=lane)
    ports = resolution.make_ports([predecessor, dependent], engine=engine)

    enqueue_dependents(ports, engine, predecessor)

    assert enqueue_lanes(engine) == [lane]


@pytest.mark.parametrize("lane", ["interactive", "walk"])
def test_the_sweep_enqueues_a_dependent_on_its_lane(lane: str) -> None:
    engine = FakeWorkflowEngine()
    predecessor = resolution.a_run("done")
    dependent = resolution.a_run("queued", after_run_ids=(predecessor.id,), lane=lane)
    ports = resolution.make_ports([predecessor, dependent], engine=engine)

    sweep_dependency_waiting(ports, engine)

    assert enqueue_lanes(engine) == [lane]


# ── AC6, the router ──────────────────────────────────────────────────────────


async def test_each_queue_item_carries_its_entrys_lane(env: dict[str, str]) -> None:
    api = Api(env)
    api.app.dependency_overrides[queue_ports] = lambda: api.ports
    walk, interactive = a_run(lane="walk"), a_run(lane="interactive")
    for run, lane in ((walk, "walk"), (interactive, "interactive")):
        api.runs.add(run)
        api.engine.queue[run.id] = QueueEntry(
            run_id=run.id, engine_state="enqueued", position=1, enqueued_at=NOW, lane=lane
        )

    async with api.client() as client:
        response = await client.get(QUEUE)

    lanes = {item["run"]["id"]: item["lane"] for item in response.json()["items"]}
    assert lanes == {str(walk.id): "walk", str(interactive.id): "interactive"}
