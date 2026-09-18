"""`create_run` probe gate (story 2-2): model validation and probe-fail rejection.

`create_run` runs the probe once after `_refuse_failing_lines` and rejects any model not
in the returned list (HTTP 422 via `Invalid`) or refuses when the probe itself fails (HTTP
409 via `Conflict`).

Two probe calls per invocation when a harness is wired: one inside `harness_probe_line()`
(pre-flight), one in `create_run`'s own model-validation block.  Each test queues exactly
the right number of `ProbeResult`s for the FakeHarness's scripted queue.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
    create_run,
)
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.domain.errors import Conflict, Invalid
from orchestrator.domain.ports.harness import ProbeResult
from tests.unit.application.templates import plan_fixtures as fixtures

# Re-use the entity builders from the sibling test module.
from tests.unit.application.test_create_run_use_case import project, repository
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)
BUDGET = Decimal("10")

#: `repo-init@1` has a `bmad.install` step (method_version_line → skip) and an `agent`
#: step (harness_probe_line → evaluated), which is the combination these tests need.
_TEMPLATE = "repo-init"
_VERSION = 1


def _probe_ok(models: list[str] | None = None) -> ProbeResult:
    return ProbeResult(
        ok=True,
        version="2.1.258",
        failing_reason=None,
        models=list(models) if models is not None else ["gpt-4o"],
    )


def _probe_fail(reason: str = "gateway unreachable") -> ProbeResult:
    return ProbeResult(ok=False, version="2.1.258", failing_reason=reason, models=[])


def _base_request(**overrides: object) -> CreateRunRequest:
    payload: dict[str, object] = {
        "template_name": _TEMPLATE,
        "template_version": _VERSION,
        "project_id": fixtures.PROJECT.id,
        "repository_id": fixtures.REPOSITORY.id,
        "base_branch": fixtures.BASE_BRANCH,
        "budget_usd": BUDGET,
        "harness": "claude",
    }
    payload.update(overrides)
    return CreateRunRequest(**payload)  # type: ignore[arg-type]


class Harness:
    """One set of fakes wired like `api/providers.py::create_run_ports`, with a
    `harness_registry` so probe-gate paths are exercised."""

    def __init__(
        self,
        *,
        probe_results: list[ProbeResult],
        skip_harness_check: bool = False,
    ) -> None:
        self.runs = FakeRunRepository()
        self.templates = FakeTemplateVersionRepository(
            list(fixtures.repository_of_versions().versions.values()), runs=self.runs
        )
        self.steps = FakeStepRunRepository()
        self.engine = FakeWorkflowEngine()
        self.uow = FakeUnitOfWork()
        self.clock = FakeClock(NOW)
        fake_harness = FakeHarness(probe_results=probe_results)
        preflight = PreflightPorts(
            git=fixtures.repo_init_git(),
            templates=self.templates,
            runs=self.runs,
            harnesses=FakeHarnessRepository(),
            repositories=FakeRepositoryRepository([repository()]),
            projects=FakeProjectRepository([project()]),
            bmad_version=fixtures.BMAD_VERSION,
            max_active_runs=2,
            work_dir=Path("/work"),
            harness_registry={"claude": fake_harness},
        )
        self.ports = CreateRunPorts(
            preflight=preflight,
            engine=self.engine,
            steps=self.steps,
            uow=self.uow,
            clock=self.clock,
            skip_harness_check=skip_harness_check,
        )

    def create(self, request: CreateRunRequest):  # type: ignore[no-untyped-def]
        with self.uow:
            return create_run(self.ports, request)


# ── (1) model in probe list → queued ────────────────────────────────────────────────────


def test_model_in_probe_list_creates_run() -> None:
    """Probe ok and model matches the returned list → run created with status 'queued'."""
    # Two probe calls: one in harness_probe_line (pre-flight), one in create_run block.
    harness = Harness(
        probe_results=[
            _probe_ok(["gpt-4o"]),  # pre-flight probe
            _probe_ok(["gpt-4o"]),  # create_run probe
        ]
    )

    result = harness.create(_base_request(model="gpt-4o"))

    assert result.run.status == "queued"


# ── (2) model not in non-empty probe list → Invalid ─────────────────────────────────────


def test_model_not_in_probe_list_raises_invalid() -> None:
    """Model not in non-empty probe list → `Invalid` naming the model and the list."""
    harness = Harness(
        probe_results=[
            _probe_ok(["gpt-4o", "claude-3"]),  # pre-flight probe — passes
            _probe_ok(["gpt-4o", "claude-3"]),  # create_run probe — triggers model check
        ]
    )

    with pytest.raises(Invalid) as exc_info:
        harness.create(_base_request(model="bad-model"))

    message = str(exc_info.value)
    assert "bad-model" in message
    assert "gpt-4o" in message or "claude-3" in message


# ── (3) probe fail at create_run → Conflict ─────────────────────────────────────────────


def test_probe_fail_at_create_raises_conflict() -> None:
    """create_run's own probe call fails → `Conflict` carrying the failing reason.

    The first probe (pre-flight's `harness_probe_line`) returns ok so the harness line
    passes; only the second probe (create_run's model-validation block) returns fail.
    """
    harness = Harness(
        probe_results=[
            _probe_ok(),  # pre-flight probe — passes
            _probe_fail("gateway unreachable"),  # create_run probe — rejected
        ]
    )

    with pytest.raises(Conflict) as exc_info:
        harness.create(_base_request(model="gpt-4o"))

    assert "gateway unreachable" in str(exc_info.value)


# ── (4) req.model=None → no model validation ────────────────────────────────────────────


def test_no_model_skips_model_validation() -> None:
    """When `req.model` is None the model-validation block is skipped entirely."""
    harness = Harness(
        probe_results=[
            _probe_ok(["gpt-4o"]),  # pre-flight probe
            _probe_ok(["gpt-4o"]),  # create_run probe — model is None, so no check
        ]
    )

    result = harness.create(_base_request(model=None))

    assert result.run.status == "queued"


# ── (5) probe ok, models=[] → no validation on empty list ───────────────────────────────


def test_empty_model_list_skips_model_validation() -> None:
    """Gateway-disabled mode: probe returns `ok=True, models=[]` → any model is accepted."""
    harness = Harness(
        probe_results=[
            _probe_ok([]),  # pre-flight probe — ok, empty list
            _probe_ok([]),  # create_run probe — empty list → skip validation
        ]
    )

    result = harness.create(_base_request(model="any-model"))

    assert result.run.status == "queued"


# ── (6) readiness run: skip_harness_check not set to True + probe ok ────────────────────


def test_readiness_without_skip_harness_check_creates_run_when_probe_ok() -> None:
    """With the `skip_harness_check=True` exemption removed from `readiness_ports`,
    a correctly-installed harness (probe ok) must still create the run successfully.

    `skip_harness_check` stays `False` (the default) — the probe replaces the exemption.
    """
    harness = Harness(
        probe_results=[
            _probe_ok(),  # pre-flight probe
            _probe_ok(),  # create_run probe
        ],
        skip_harness_check=False,  # no exemption — explicit to document intent
    )

    result = harness.create(_base_request(model="gpt-4o"))

    assert result.run.status == "queued"
