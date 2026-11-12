"""`POST /api/v1/spec-folders/validate` (epic 2 story 3, 2026-11-12, AD-35, AC-13)."""

from __future__ import annotations

import httpx
import pytest

from orchestrator.api.routers import spec_folders as router_module
from orchestrator.api.schemas import spec_folders as schemas_module
from orchestrator.application import findings
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import PlanError, ResolvedTree
from orchestrator.application.templates.validate import validate
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

assert router_module.router is not None
assert schemas_module.MAX_FILES

HTTP_OK = 200
URL = "/api/v1/spec-folders/validate"
FOLDER = fixtures.SPEC_FOLDER
LIST_PATH = f"{FOLDER}/stories.yaml"

DUPLICATES = '- {id: "3", title: A, description: d}\n- {id: "3", title: B, description: d}\n'

TEMPLATE = """
name: equivalence
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  branch:      { type: string,     required: true }
  spec_folder: { type: path,       required: true }
steps:
  - id: stories
    for_each: "{{spec_folder}}/stories.yaml"
    as: story
    steps:
      - id: sync
        uses: git.sync
        gate: deterministic
"""


async def post(env: dict[str, str], files: dict[str, str]) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    headers = {"Authorization": f"Bearer {env['ORCHESTRATOR_TOKEN']}"}
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.post(URL, json={"files": files}, headers=headers)


def planned_error() -> PlanError:
    templates = FakeTemplateVersionRepository()
    result = validate(TEMPLATE, templates=templates)
    assert result.template is not None, result.errors
    git = FakeGit(
        refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA},
        files={(fixtures.BASE_SHA, LIST_PATH): DUPLICATES},
    )
    run_inputs = fixtures.inputs(values={"spec_folder": FOLDER})
    with pytest.raises(PlanError) as raised:
        plan_run(
            ResolvedTree(root=result.template),
            run_inputs,
            git=git,
            base_dir=fixtures.BASE,
            bmad_version=fixtures.BMAD_VERSION,
        )
    return raised.value


async def test_the_route_and_the_plan_report_the_same_defect(env: dict[str, str]) -> None:
    response = await post(env, {LIST_PATH: DUPLICATES, f"{FOLDER}/SPEC.md": "# s\n"})
    error = planned_error()

    assert response.status_code == HTTP_OK
    found = response.json()["findings"]
    assert [f["code"] for f in found] == ["spec-duplicate-entry-id"]
    assert found[0]["path"] == LIST_PATH
    assert findings.code_for(error.reason) == "spec-duplicate-entry-id"
    assert error.file == LIST_PATH
    assert error.item == "3"
    assert error.template == "equivalence"
    assert error.line is not None


async def test_a_clean_folder_answers_no_finding(env: dict[str, str]) -> None:
    files = {
        "epics.yaml": "- {id: e1, title: One, branch: feat/e1, spec_folder: e1}\n",
        "e1/stories.yaml": '- {id: "1", title: T, description: d}\n',
        "e1/SPEC.md": "# s\n",
        "e1/stories/1-first.md": "x",
    }
    response = await post(env, files)
    assert (response.status_code, response.json()) == (HTTP_OK, {"findings": []})


async def test_a_missing_spec_md_is_a_refusal_coded_finding(env: dict[str, str]) -> None:
    response = await post(env, {LIST_PATH: '- {id: "3", title: A, description: d}\n'})
    (found,) = response.json()["findings"]
    assert found["code"] == findings.REFUSAL_SPEC_MD_MISSING
    assert found["guide"] == f"errors/{findings.REFUSAL_SPEC_MD_MISSING}"
    assert found["path"] == f"{FOLDER}/SPEC.md"


def test_the_contract_publishes_the_request_and_the_answer(env: dict[str, str]) -> None:
    schema = create_app(Settings()).openapi()
    post_op = schema["paths"][URL]["post"]
    body = schema["components"]["schemas"]["SpecFolderIn"]
    assert body["required"] == ["files"]
    assert body["properties"]["files"]["additionalProperties"] == {"type": "string"}
    out = schema["components"]["schemas"]["SpecFolderCheckOut"]
    assert out["properties"]["findings"]["items"] == {"$ref": "#/components/schemas/ProblemError"}
    assert "200" in post_op["responses"]
