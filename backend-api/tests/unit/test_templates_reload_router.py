"""`POST /api/v1/templates/reload` over an ASGI transport (SPEC CAP-5, D3)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import template_ports
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.use_cases import template_judge
from orchestrator.application.use_cases.plan_run import resolve_tree
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.domain.entities.template import TemplateRef
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ports.template_folders import OperatorFolder
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.templates_loader import FilesystemTemplateFolders
from orchestrator.main import create_app
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.template_folders import FakeTemplateFolders, file, ready
from tests.unit.fakes.templates import FakeTemplateVersionRepository

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_CONFLICT = 409
RELOAD = "/api/v1/templates/reload"
TEMPLATES = "/api/v1/templates"
SECOND = 2

BENCH = """name: bench
version: 1
inputs:
  initiative_folder: { type: path, required: true }
steps:
  - id: epics
    for_each: "{{initiative_folder}}/epics.yaml"
    as: epic
    bind: { spec_folder: "{{initiative_folder}}/{{epic.spec_folder}}" }
    steps:
      - id: stories
        for_each: "{{spec_folder}}/stories.yaml"
        as: story
        steps:
          - id: build
            uses: agent
            with:
              harness: claude
              skill: bmad-build-auto
            prompts:
              dispatch: "Run the skill {skill}: spec folder {spec_folder}, story id {story_id}."
              rendered: "The workflow for skill {skill} is rendered at {path}; read and follow it."
            gate: liveness
"""
EDITED = BENCH.replace("name: bench\n", "name: bench\ndescription: edited\n")
MARKER = "name: marker\nversion: 1\nsteps: []\n"
FOLDER = "initiatives/x"
EPICS = "- id: e1\n  title: First\n  branch: feat/x\n  spec_folder: e1\n"
EPICS += "- id: e2\n  title: Second\n  branch: feat/x\n  spec_folder: e2\n"
STORIES = '- id: "1"\n  title: One\n  description: first\n'
STORIES += '- id: "2"\n  title: Two\n  description: second\n'
SAVED = (
    "name: bench\nversion: 2\ndescription: saved\n"
    "steps:\n  - id: s\n    uses: git.sync\n    gate: deterministic\n"
)


class Harness:
    def __init__(self, env: dict[str, str], folders: Any = None) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.uow = FakeUnitOfWork()
        self.templates = FakeTemplateVersionRepository()
        self.folders = folders
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[template_ports] = self._ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _ports(self) -> TemplatePorts:
        if not self.uow.calls or self.uow.calls[-1] == "exit":
            self.uow.__enter__()
        return TemplatePorts(
            uow=self.uow, templates=self.templates, clock=FakeClock(), folders=self.folders
        )

    def client(self, *, bearer: bool = True) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self.token}"} if bearer else {}
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers=headers,
        )


def harness(env: dict[str, str], *files: Any, path: str = "/folder") -> Harness:
    return Harness(env, FakeTemplateFolders(folder=ready(*files, path=path)))


def remote() -> FakeGit:
    files = {(fixtures.BASE_SHA, f"{FOLDER}/epics.yaml"): EPICS}
    for epic in ("e1", "e2"):
        files[(fixtures.BASE_SHA, f"{FOLDER}/{epic}/stories.yaml")] = STORIES
    return FakeGit(refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA}, files=files, listings={})


async def test_a_new_file_is_stored_listed_and_plans_one_frame_per_item(
    env: dict[str, str],
) -> None:
    api = harness(env, file("bench", BENCH))

    async with api.client() as client:
        response = await client.post(RELOAD)
        listing = await client.get(TEMPLATES)

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["folder"] == "/folder"
    assert body["stored"] == [
        {"name": "bench", "version": 1, "file": "bench.yaml", "overrides_shipped": False}
    ]
    assert body["unchanged"] == body["refused"] == body["not_in_folder"] == []
    assert [item["name"] for item in listing.json()["items"]] == ["bench"]
    tree = resolve_tree(api.templates, TemplateRef(name="bench", version=1))
    plan = plan_run(
        tree,
        fixtures.inputs(values={"initiative_folder": FOLDER}),
        git=remote(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )
    assert [row.path for row in plan.rows if row.kind == "agent"] == [
        "epics[0].stories[0].build",
        "epics[0].stories[1].build",
        "epics[1].stories[0].build",
        "epics[1].stories[1].build",
    ]
    assert api.uow.committed


async def test_an_edit_is_version_two_and_the_second_reload_is_unchanged(
    env: dict[str, str],
) -> None:
    api = harness(env, file("bench", BENCH))
    async with api.client() as client:
        await client.post(RELOAD)
        first_text = api.templates.get("bench", 1).yaml  # type: ignore[union-attr]
        api.folders.folder = ready(file("bench", EDITED))
        edited = (await client.post(RELOAD)).json()
        again = (await client.post(RELOAD)).json()

    assert [(e["name"], e["version"]) for e in edited["stored"]] == [("bench", SECOND)]
    assert api.templates.get("bench", 1).yaml == first_text  # type: ignore[union-attr]
    assert again["stored"] == []
    assert [e["name"] for e in again["unchanged"]] == ["bench"]


async def test_a_web_saved_version_stays_listed_beside_the_folders_next_version(
    env: dict[str, str],
) -> None:
    api = harness(env, file("bench", BENCH))
    async with api.client() as client:
        await client.post(RELOAD)
        saved = await client.post(f"{TEMPLATES}/bench/versions", json={"yaml": SAVED})
        reloaded = (await client.post(RELOAD)).json()
        versions = (await client.get(f"{TEMPLATES}/bench/versions")).json()

    assert saved.status_code == httpx.codes.CREATED
    assert [(e["name"], e["version"]) for e in reloaded["stored"]] == [("bench", 3)]
    assert versions["items"] == [1, SECOND, 3]
    assert api.templates.get("bench", 3).yaml == BENCH  # type: ignore[union-attr]


async def test_a_concurrent_save_is_a_409_naming_the_pair_and_commits_nothing(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api = harness(env, file("bench", BENCH))

    def taken(*_: object, **__: object) -> None:
        raise Conflict("template version bench@1 taken by a concurrent save; nothing stored")

    monkeypatch.setattr(api.templates, "add_version", taken)
    async with api.client() as client:
        response = await client.post(RELOAD)

    assert response.status_code == HTTP_CONFLICT
    assert "bench@1" in response.json()["detail"]
    assert not api.uow.committed


async def test_unparsable_files_a_judge_failure_and_unsafe_names_are_refused_not_raised(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    real = template_judge.validate

    def exploding(text: str, *, templates: object, root_version: int | None = None) -> object:
        if "name: marker" in text:
            raise KeyError("boom")
        return real(text, templates=templates, root_version=root_version)  # type: ignore[arg-type]

    monkeypatch.setattr(template_judge, "validate", exploding)
    api = harness(
        env,
        file("bad-date", "x: 2026-02-30\n"),
        file("bad-stamp", "x: !!timestamp foo\n"),
        file("marker", MARKER),
    )
    async with api.client() as client:
        response = await client.post(RELOAD)

    assert response.status_code == HTTP_OK
    refused = {r["file"]: r["errors"] for r in response.json()["refused"]}
    for name in ("bad-date.yaml", "bad-stamp.yaml"):
        assert [(e["line"], e["reason"]) for e in refused[name]] == [(1, "invalid yaml")]
    assert [e["reason"] for e in refused["marker.yaml"]] == ["invalid template"]


@pytest.mark.skipif(sys.platform != "linux", reason="needs a filesystem that keeps raw bytes")
async def test_a_file_name_that_is_not_utf8_is_a_safe_display_name(
    env: dict[str, str], tmp_path: Path
) -> None:
    operator = tmp_path / "operator"
    operator.mkdir()
    try:
        with open(os.path.join(os.fsencode(operator), b"bad\xff.yaml"), "w") as handle:
            handle.write("name: x\n")
    except OSError:
        pytest.skip("the filesystem refuses the name")
    api = Harness(env, FilesystemTemplateFolders(tmp_path / "shipped", operator))

    async with api.client() as client:
        response = await client.post(RELOAD)

    assert response.status_code == HTTP_OK
    names = [r["file"] for r in json.loads(response.text)["refused"]]
    assert any("\\xff" in name for name in names)


async def test_reload_without_the_bearer_is_a_401(env: dict[str, str]) -> None:
    async with harness(env).client(bearer=False) as client:
        assert (await client.post(RELOAD)).status_code == HTTP_UNAUTHORIZED


@pytest.mark.parametrize("folders", [None, FakeTemplateFolders()])
async def test_an_off_folder_or_no_folder_port_is_a_409(env: dict[str, str], folders: Any) -> None:
    async with Harness(env, folders).client() as client:
        response = await client.post(RELOAD)

    assert response.status_code == HTTP_CONFLICT
    assert response.json()["detail"] == "template folder not configured"


async def test_a_missing_folder_is_a_409_ending_with_its_path(env: dict[str, str]) -> None:
    folders = FakeTemplateFolders(folder=OperatorFolder(path="/gone/here", state="missing"))
    async with Harness(env, folders).client() as client:
        response = await client.post(RELOAD)

    assert response.status_code == HTTP_CONFLICT
    detail = response.json()["detail"]
    assert detail.startswith("template folder not found: ")
    assert detail.endswith("/gone/here")


async def test_the_published_operation_has_a_summary_a_409_and_no_get(
    env: dict[str, str],
) -> None:
    async with harness(env).client() as client:
        document = (await client.get("/openapi.json")).json()

    path = document["paths"][RELOAD]
    assert list(path) == ["post"]
    assert path["post"]["summary"]
    assert "409" in path["post"]["responses"]
