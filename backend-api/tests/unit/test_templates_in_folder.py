"""`in_folder` on the template reads (story 6, BR-17, AC-13 notice part, 2026-11-06)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from orchestrator.api.providers import template_ports
from orchestrator.api.schemas.templates import TemplateSummaryOut, TemplateVersionOut
from orchestrator.application.use_cases import templates as use_cases
from orchestrator.application.use_cases.templates import TemplatePorts, TemplateVersionDetail
from orchestrator.domain.entities.template import TemplateSummary, TemplateVersion
from orchestrator.domain.ports.template_folders import OperatorFolder
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.templates_loader import FilesystemTemplateFolders
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.template_folders import FakeTemplateFolders, file, ready
from tests.unit.fakes.templates import FakeTemplateVersionRepository

HTTP_OK = 200
HTTP_CREATED = 201
TEMPLATES = "/api/v1/templates"
SMOKE = "agent-smoke"
BODY = (
    "name: {n}\nversion: {v}\nsteps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
)


class Harness:
    def __init__(self, env: dict[str, str], folders: Any) -> None:
        settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.uow = FakeUnitOfWork()
        self.templates = FakeTemplateVersionRepository()
        self.clock = FakeClock()
        self.folders = folders
        self.app = create_app(settings)
        self.app.dependency_overrides[template_ports] = self._ports
        self.token = env["ORCHESTRATOR_TOKEN"]
        for name in (SMOKE, "plain"):
            self.templates.add(
                TemplateVersion(
                    name=name,
                    version=1,
                    yaml=BODY.format(n=name, v=1),
                    hash=f"sha-{name}",
                    created_at=self.clock.now(),
                )
            )

    def _ports(self) -> TemplatePorts:
        if not self.uow.calls or self.uow.calls[-1] == "exit":
            self.uow.__enter__()
        return TemplatePorts(
            uow=self.uow, templates=self.templates, clock=self.clock, folders=self.folders
        )

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


async def read_all(api: Harness) -> tuple[Any, Any, Any]:
    async with api.client() as client:
        listing = await client.get(TEMPLATES)
        one = await client.get(f"{TEMPLATES}/{SMOKE}/1")
        saved = await client.post(
            f"{TEMPLATES}/{SMOKE}/versions", json={"yaml": BODY.format(n=SMOKE, v=2)}
        )
    assert listing.status_code == HTTP_OK
    assert one.status_code == HTTP_OK
    assert saved.status_code == HTTP_CREATED
    return listing.json(), one.json(), saved.json()


@pytest.mark.parametrize("text", ["name: agent-smoke\n", "not: [valid\n"])
async def test_a_readable_file_of_the_name_sets_in_folder_on_all_three_routes(
    env: dict[str, str], text: str
) -> None:
    api = Harness(env, FakeTemplateFolders(folder=ready(file(SMOKE, text))))

    listing, one, saved = await read_all(api)

    flags = {item["name"]: item["in_folder"] for item in listing["items"]}
    assert flags == {SMOKE: True, "plain": False}
    assert one["in_folder"] is True
    assert saved["in_folder"] is True


@pytest.mark.parametrize(
    "folders",
    [
        FakeTemplateFolders(folder=ready(file("other", "x"))),
        FakeTemplateFolders(folder=ready(file(SMOKE, "", read_error="denied"))),
        FakeTemplateFolders(folder=OperatorFolder(path="", state="off")),
        FakeTemplateFolders(folder=OperatorFolder(path="/gone", state="missing")),
        None,
    ],
    ids=["other-file", "read-error", "off", "missing", "no-port"],
)
async def test_no_readable_file_of_the_name_means_in_folder_false(
    env: dict[str, str], folders: Any
) -> None:
    listing, one, saved = await read_all(Harness(env, folders))

    assert [item["in_folder"] for item in listing["items"]] == [False, False]
    assert one["in_folder"] is False
    assert saved["in_folder"] is False


def test_folder_stems_is_empty_without_a_folders_port() -> None:
    ports = TemplatePorts(
        uow=FakeUnitOfWork(), templates=FakeTemplateVersionRepository(), clock=FakeClock()
    )

    assert use_cases.folder_stems(ports) == frozenset()


def test_folder_stems_names_readable_files_only() -> None:
    folders = FakeTemplateFolders(folder=ready(file("a", "x"), file("b", "", read_error="denied")))
    ports = TemplatePorts(
        uow=FakeUnitOfWork(),
        templates=FakeTemplateVersionRepository(),
        clock=FakeClock(),
        folders=folders,
    )

    assert use_cases.folder_stems(ports) == frozenset({"a"})


def test_the_real_adapter_answers_no_stems_for_a_path_that_does_not_exist(tmp_path: Path) -> None:
    adapter = FilesystemTemplateFolders(templates_dir=tmp_path, operator_dir=tmp_path / "absent")

    assert adapter.operator_stems() == frozenset()


def test_of_defaults_in_folder_to_false_and_takes_an_explicit_value() -> None:
    summary = TemplateSummary(name="a", description=None, latest_version=1, versions=[1])
    assert TemplateSummaryOut.of(summary).in_folder is False
    assert TemplateSummaryOut.of(summary, in_folder=True).in_folder is True

    template = TemplateVersion(
        name="a",
        version=1,
        yaml=BODY.format(n="a", v=1),
        hash="h",
        created_at=datetime(2026, 11, 6, tzinfo=UTC),
    )
    detail = TemplateVersionDetail(template=template, called_by=(), pinned_by=0, inputs=())
    assert TemplateVersionOut.of(detail).in_folder is False
    assert TemplateVersionOut.of(detail, in_folder=True).in_folder is True
