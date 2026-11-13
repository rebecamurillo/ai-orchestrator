"""Findings leave the API with `code` and `guide` (story 1, AD-15 amended 2026-11-11)."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.errors import Problem, ProblemDetail, ProblemError, finding_error
from orchestrator.api.providers import template_ports
from orchestrator.api.schemas.runs import plan_error_problems
from orchestrator.application import findings
from orchestrator.application.templates.plan_model import DUPLICATE_ENTRY_ID, PlanError
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.templates import FakeTemplateVersionRepository

HTTP_OK = 200
HTTP_UNPROCESSABLE = 422
UNKNOWN_KEY_YAML = (
    "name: leaf\nversion: 1\nbogus: 1\nsteps:\n  - id: sync\n    uses: git.sync\n"
    "    gate: deterministic\n"
)


class Harness:
    def __init__(self, env: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.uow = FakeUnitOfWork()
        self.templates = FakeTemplateVersionRepository()
        self.clock = FakeClock()
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[template_ports] = self._ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _ports(self) -> TemplatePorts:
        if not self.uow.calls or self.uow.calls[-1] == "exit":
            self.uow.__enter__()
        return TemplatePorts(uow=self.uow, templates=self.templates, clock=self.clock)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api(env: dict[str, str]) -> Harness:
    return Harness(env)


async def test_ac1_an_unknown_key_carries_its_code_and_guide(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post(
            "/api/v1/templates/leaf/validate", json={"yaml": UNKNOWN_KEY_YAML}
        )

    assert response.status_code == HTTP_OK
    finding = next(item for item in response.json()["errors"] if item["reason"] == "unknown key")
    assert finding["line"] == 3  # noqa: PLR2004
    assert finding["code"] == "template-unknown-key"
    assert finding["guide"] == "errors/template-unknown-key"
    assert findings.entry("template-unknown-key")


async def test_ac5_a_refused_request_body_carries_no_code(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post("/api/v1/templates/leaf/validate", json={"nope": 1})

    assert response.status_code == HTTP_UNPROCESSABLE
    for item in response.json()["errors"]:
        assert "code" not in item
        assert "guide" not in item


def test_finding_error_with_an_uncoded_reason_has_no_code() -> None:
    error = finding_error(reason="git said no", path="x")

    assert error.code is None
    assert error.guide is None
    assert error.path == "x"


def test_finding_error_with_a_known_reason_sets_both() -> None:
    error = finding_error(reason="unknown key", template="t", version="1", line=4)

    assert (error.template, error.version, error.line) == ("t", "1", 4)
    assert error.code == "template-unknown-key"
    assert error.guide == "errors/template-unknown-key"


def test_problem_detail_carries_code_and_guide_only_when_set() -> None:
    plain = ProblemDetail(title="t", status=400).as_body()
    coded = ProblemDetail(
        title="t", status=400, code="template-unknown-key", guide="errors/template-unknown-key"
    ).as_body()

    assert "code" not in plain
    assert "guide" not in plain
    assert coded["code"] == "template-unknown-key"
    assert coded["guide"] == "errors/template-unknown-key"


def test_problem_round_trips_code_and_guide() -> None:
    problem = Problem(status=422, title="t", code="spec-x", guide="errors/spec-x")

    detail = problem.as_detail()

    assert (detail.code, detail.guide) == ("spec-x", "errors/spec-x")
    assert Problem(status=422, title="t").as_detail().code is None


def test_a_plan_error_problem_carries_its_code_and_guide() -> None:
    coded = plan_error_problems(PlanError(reason=DUPLICATE_ENTRY_ID, item="e1", line=2))
    uncoded = plan_error_problems(PlanError(reason="git said no"))

    assert [(e.path, e.line, e.code, e.guide) for e in coded] == [
        (
            "e1",
            2,
            findings.SPEC_DUPLICATE_ENTRY_ID,
            "errors/spec-duplicate-entry-id",
        )
    ]
    assert [(e.code, e.guide) for e in uncoded] == [(None, None)]


def test_a_problem_error_without_code_drops_it_from_the_body() -> None:
    body = ProblemDetail(title="t", status=1, errors=[ProblemError(reason="r")]).as_body()

    assert body["errors"] == [{"reason": "r"}]
