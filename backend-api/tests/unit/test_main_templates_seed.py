"""`main.py`'s `run_migrations` and `seed_shipped_templates` — the SPEC CAP-3 start-up step.

`main.run_migrations` wraps `infrastructure.db.migrations.run_migrations` with the seed, and
`tests/unit/test_migrations.py` proves "migrate before bind" by replacing `main.run_migrations`
wholesale — this module is where the *wrapping itself* is pinned: both steps run, in order,
and neither ever needs a real database, because every collaborator here is a fake or a
recording stand-in (AD-18). `main.py` is exempt from `scripts/check_test_pairs.py`
(the composition root), so this module exists for correctness, not to satisfy that gate.
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator import main as main_module
from orchestrator.application.use_cases.templates import SeedResult
from orchestrator.infrastructure.logging import configure_logging
from orchestrator.infrastructure.settings import Settings


class _Recorder:
    def __init__(self) -> None:
        self.order: list[str] = []


@pytest.fixture
def recorder() -> _Recorder:
    return _Recorder()


class FakeSession:
    pass


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class FakeUow:
    def __init__(self, factory: Any) -> None:
        self.factory = factory

    def __enter__(self) -> FakeUow:
        self.session = FakeSession()
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def test_run_migrations_migrates_then_seeds_and_returns_the_head(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, recorder: _Recorder
) -> None:
    """Pins all three start-up collaborators, in order (SPEC CAP-3, story 4.3 adds the
    harness seed beside the template one). `Settings()` here still carries the real,
    unreachable `.env.example` `DATABASE_URL` (AD-20) — a fourth collaborator added to
    `run_migrations` without a matching `monkeypatch.setattr` here would reach it for real
    and raise, failing this test outright rather than letting `recorder.order` pass quietly
    short of the truth."""

    def fake_migrate(settings: Settings) -> str:
        recorder.order.append("migrate")
        return "0004_template"

    def fake_seed(settings: Settings) -> list[SeedResult]:
        recorder.order.append("seed")
        return []

    def fake_harness_seed(settings: Settings) -> list[Any]:
        recorder.order.append("harness")
        return []

    monkeypatch.setattr(main_module.db_migrations, "run_migrations", fake_migrate)
    monkeypatch.setattr(main_module, "seed_shipped_templates", fake_seed)
    monkeypatch.setattr(main_module, "seed_harness_table", fake_harness_seed)

    head = main_module.run_migrations(Settings())

    assert recorder.order == ["migrate", "seed", "harness"]
    assert head == "0004_template"


def test_run_migrations_never_seeds_when_the_migration_fails(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, recorder: _Recorder
) -> None:
    def exploding_migrate(settings: Settings) -> str:
        raise RuntimeError("relation already exists")

    def fake_seed(settings: Settings) -> list[SeedResult]:
        recorder.order.append("seed")
        return []

    monkeypatch.setattr(main_module.db_migrations, "run_migrations", exploding_migrate)
    monkeypatch.setattr(main_module, "seed_shipped_templates", fake_seed)

    with pytest.raises(RuntimeError, match="relation already exists"):
        main_module.run_migrations(Settings())

    assert recorder.order == []


def test_seed_shipped_templates_reads_the_configured_directory(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_loader(templates_dir: Any) -> list[tuple[str, str]]:
        captured["templates_dir"] = templates_dir
        return [("leaf", "name: leaf\nversion: 1\nsteps: []\n")]

    class FakeRepo:
        def __init__(self, session: Any) -> None:
            captured["session"] = session

    def fake_seed_shipped(ports: Any, files: Any) -> list[SeedResult]:
        captured["ports"] = ports
        captured["files"] = files
        return [SeedResult(name="leaf", inserted_as=1)]

    engine = FakeEngine()
    monkeypatch.setattr(main_module, "load_shipped_templates", fake_loader)
    monkeypatch.setattr(main_module, "create_engine_from", lambda settings: engine)
    monkeypatch.setattr(main_module, "SQLAlchemyUnitOfWork", FakeUow)
    monkeypatch.setattr(main_module, "SQLAlchemyTemplateVersionRepository", FakeRepo)
    monkeypatch.setattr(main_module, "seed_shipped", fake_seed_shipped)

    settings = Settings()
    results = main_module.seed_shipped_templates(settings)

    assert captured["templates_dir"] == settings.templates_dir
    assert captured["files"] == [("leaf", "name: leaf\nversion: 1\nsteps: []\n")]
    assert isinstance(captured["ports"].templates, FakeRepo)
    assert captured["ports"].clock is not None
    assert results == [SeedResult(name="leaf", inserted_as=1)]


def test_seed_shipped_templates_disposes_its_own_engine(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = FakeEngine()
    monkeypatch.setattr(main_module, "load_shipped_templates", lambda templates_dir: [])
    monkeypatch.setattr(main_module, "create_engine_from", lambda settings: engine)
    monkeypatch.setattr(main_module, "SQLAlchemyUnitOfWork", FakeUow)
    monkeypatch.setattr(
        main_module, "SQLAlchemyTemplateVersionRepository", lambda session: object()
    )
    monkeypatch.setattr(main_module, "seed_shipped", lambda ports, files: [])

    main_module.seed_shipped_templates(Settings())

    assert engine.disposed is True


def test_seed_shipped_templates_disposes_its_engine_even_when_seeding_raises(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = FakeEngine()

    def exploding_seed(ports: Any, files: Any) -> list[SeedResult]:
        raise RuntimeError("a shipped file is invalid")

    monkeypatch.setattr(main_module, "load_shipped_templates", lambda templates_dir: [])
    monkeypatch.setattr(main_module, "create_engine_from", lambda settings: engine)
    monkeypatch.setattr(main_module, "SQLAlchemyUnitOfWork", FakeUow)
    monkeypatch.setattr(
        main_module, "SQLAlchemyTemplateVersionRepository", lambda session: object()
    )
    monkeypatch.setattr(main_module, "seed_shipped", exploding_seed)

    with pytest.raises(RuntimeError, match="a shipped file is invalid"):
        main_module.seed_shipped_templates(Settings())

    assert engine.disposed is True


def test_seed_shipped_templates_logs_only_the_newly_inserted(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(main_module, "load_shipped_templates", lambda templates_dir: [("leaf", "")])
    monkeypatch.setattr(main_module, "create_engine_from", lambda settings: FakeEngine())
    monkeypatch.setattr(main_module, "SQLAlchemyUnitOfWork", FakeUow)
    monkeypatch.setattr(
        main_module, "SQLAlchemyTemplateVersionRepository", lambda session: object()
    )
    monkeypatch.setattr(
        main_module,
        "seed_shipped",
        lambda ports, files: [
            SeedResult(name="leaf", inserted_as=1),
            SeedResult(name="story", inserted_as=None),
        ],
    )
    configure_logging("info")

    main_module.seed_shipped_templates(Settings())

    out = capsys.readouterr().out
    assert "shipped template leaf seeded as v1" in out
    assert '"name": "leaf"' in out
    assert '"version": 1' in out
    assert "story" not in out


def test_seed_shipped_templates_warns_when_the_directory_has_nothing(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(main_module, "load_shipped_templates", lambda templates_dir: [])
    monkeypatch.setattr(main_module, "create_engine_from", lambda settings: FakeEngine())
    monkeypatch.setattr(main_module, "SQLAlchemyUnitOfWork", FakeUow)
    monkeypatch.setattr(
        main_module, "SQLAlchemyTemplateVersionRepository", lambda session: object()
    )
    monkeypatch.setattr(main_module, "seed_shipped", lambda ports, files: [])
    configure_logging("info")

    main_module.seed_shipped_templates(Settings())

    out = capsys.readouterr().out
    assert "no shipped templates found" in out


def test_seed_shipped_templates_does_not_warn_when_files_are_found(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(main_module, "load_shipped_templates", lambda templates_dir: [("leaf", "")])
    monkeypatch.setattr(main_module, "create_engine_from", lambda settings: FakeEngine())
    monkeypatch.setattr(main_module, "SQLAlchemyUnitOfWork", FakeUow)
    monkeypatch.setattr(
        main_module, "SQLAlchemyTemplateVersionRepository", lambda session: object()
    )
    monkeypatch.setattr(main_module, "seed_shipped", lambda ports, files: [])
    configure_logging("info")

    main_module.seed_shipped_templates(Settings())

    out = capsys.readouterr().out
    assert "no shipped templates found" not in out
