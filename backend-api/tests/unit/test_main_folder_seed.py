"""The start-up folder pass (story 4, AD-26): `run_migrations` runs it right after the shipped
pass, only when `OPERATOR_TEMPLATES_DIR` is set; a refused file or a lost race is a warning and
never stops start-up; any other error does."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from structlog.testing import capture_logs

from orchestrator import main as main_module
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ports.template_folders import OperatorFolder
from orchestrator.infrastructure import template_folder_seed as seed_module
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.template_folders import FakeTemplateFolders, file, ready
from tests.unit.fakes.templates import FakeTemplateVersionRepository

STEP = "steps:\n  - id: s\n    uses: git.sync\n    gate: deterministic\n"
GOOD = "name: good\nversion: 1\n" + STEP
BAD = "name: bad\nversion: 1\nsteps: []\n"


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class FakeUow:
    instances: list[FakeUow]

    def __init__(self, factory: Any) -> None:
        self.session = object()
        self.committed = False
        FakeUow.instances.append(self)

    def __enter__(self) -> FakeUow:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def commit(self) -> None:
        self.committed = True


class World:
    def __init__(self, folder: OperatorFolder, repo: FakeTemplateVersionRepository) -> None:
        self.folders = FakeTemplateFolders(folder=folder)
        self.repo = repo
        self.engine = FakeEngine()


@pytest.fixture
def world(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> World:
    FakeUow.instances = []
    built = World(ready(file("good", GOOD), file("bad", BAD)), FakeTemplateVersionRepository())
    monkeypatch.setattr(seed_module, "create_engine_from", lambda settings: built.engine)
    monkeypatch.setattr(seed_module, "create_session_factory", lambda engine: object())
    monkeypatch.setattr(seed_module, "SQLAlchemyUnitOfWork", FakeUow)
    monkeypatch.setattr(seed_module, "SQLAlchemyTemplateVersionRepository", lambda s: built.repo)
    monkeypatch.setattr(seed_module, "FilesystemTemplateFolders", lambda *a: built.folders)
    return built


def settings(dir_: str | None) -> Settings:
    return Settings(operator_templates_dir=Path(dir_) if dir_ else None)  # type: ignore[call-arg]


def test_unset_means_no_folder_pass_at_all(world: World) -> None:
    assert seed_module.seed_folder_templates(settings(None)) is None

    assert world.folders.operator_calls == 0
    assert FakeUow.instances == []
    assert world.engine.disposed is False


def test_a_valid_and_an_invalid_file_store_one_warn_one_and_commit(world: World) -> None:
    with capture_logs() as logs:
        outcome = seed_module.seed_folder_templates(settings("/ops"))

    assert outcome is not None
    assert [e.name for e in outcome.stored] == ["good"]
    assert world.repo.list_versions("good") == [1]
    (uow,) = FakeUow.instances
    assert uow.committed is True
    assert world.engine.disposed is True
    warnings = [log for log in logs if log["log_level"] == "warning"]
    assert len(warnings) == 1
    assert "bad.yaml" in warnings[0]["event"]
    assert world.folders.operator_calls == 1


def test_a_lost_race_is_one_warning_and_nothing_is_committed(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def racing(version: object, *, description: str | None) -> None:
        raise Conflict("template version good@1 taken by a concurrent save; nothing stored")

    monkeypatch.setattr(world.repo, "add_version", racing)

    with capture_logs() as logs:
        assert seed_module.seed_folder_templates(settings("/ops")) is None

    assert [log["log_level"] for log in logs] == ["warning"]
    assert FakeUow.instances[0].committed is False
    assert world.engine.disposed is True


def test_a_configured_but_missing_folder_is_one_warning_and_stores_nothing(
    world: World,
) -> None:
    world.folders.folder = OperatorFolder(path="/ops", state="missing")

    with capture_logs() as logs:
        assert seed_module.seed_folder_templates(settings("/ops")) is None

    assert [log["log_level"] for log in logs] == ["warning"]
    assert world.repo.versions == {}
    assert FakeUow.instances == []


def test_a_removed_file_is_an_info_line_and_a_non_conflict_error_raises(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_module.seed_folder_templates(settings("/ops"))
    world.folders.folder = ready()

    with capture_logs() as logs:
        seed_module.seed_folder_templates(settings("/ops"))

    assert any("good" in log["event"] and log["log_level"] == "info" for log in logs)

    def down(source: str) -> frozenset[str]:
        raise RuntimeError("database down")

    monkeypatch.setattr(world.repo, "names_with_source", down)
    with pytest.raises(RuntimeError, match="database down"):
        seed_module.seed_folder_templates(settings("/ops"))
    assert world.engine.disposed is True


def test_run_migrations_runs_the_folder_pass_only_for_a_configured_folder(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    monkeypatch.setattr(main_module.db_migrations, "run_migrations", lambda s: "head")
    monkeypatch.setattr(main_module, "install_operator_skills", lambda s: [])
    monkeypatch.setattr(main_module, "seed_shipped_templates", lambda s: order.append("shipped"))
    monkeypatch.setattr(main_module, "seed_harness_table", lambda s: order.append("harness"))
    monkeypatch.setattr(main_module, "launch_engine", lambda: None)
    monkeypatch.setattr(main_module, "schedule_jobs", lambda s: None)
    monkeypatch.setattr(main_module, "schedule_engine_jobs", lambda s: None)
    monkeypatch.setattr(main_module, "dependency_startup_sweep", lambda s: None)

    main_module.run_migrations(settings(None))
    assert world.folders.operator_calls == 0
    main_module.run_migrations(settings("/ops"))

    assert world.folders.operator_calls == 1
    assert order == ["shipped", "harness", "shipped", "harness"]
    assert world.repo.list_versions("good") == [1]
