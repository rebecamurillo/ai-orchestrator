"""`alembic upgrade head` runs once, at start-up, before the server binds.

When migrations run, and why they are wired the way they are, is stated once in
`orchestrator.infrastructure.db.migrations`. None of it is visible by reading the code, so
this module asserts it: the ordering by driving the start-up step the way uvicorn does and
recording what happened when, and the Alembic wiring against the committed `alembic.ini`
and revision directory.

Every assertion here is written to stay true as later stories add revisions. A test that
said "there is exactly one revision" would be a trap: anchors are read-only, so the story
that adds the second one could not fix it and would be reported blocked instead.

What this module cannot prove is that a migration ever reached a database — every test
below stubs `command.upgrade`. That claim is closed in `tests/e2e/test_migrations.py`,
at the one boundary where a database exists.
"""

from __future__ import annotations

import ast
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from mako.template import Template

from orchestrator import main as main_module
from orchestrator.infrastructure.db import migrations
from orchestrator.infrastructure.db.migrations import (
    BASELINE_REVISION,
    alembic_config,
    head_revision,
    run_migrations,
)
from orchestrator.infrastructure.logging import configure_logging
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.conftest import REPO_ROOT

BACKEND_ROOT = REPO_ROOT / "backend-api"
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
VERSIONS = BACKEND_ROOT / "alembic" / "versions"


# ── the committed migration tree ─────────────────────────────────────────────


def test_the_configuration_file_is_committed() -> None:
    assert ALEMBIC_INI.is_file()


def test_no_database_url_is_committed() -> None:
    """The URL carries POSTGRES_PASSWORD; it is read from settings, never from a file."""
    text = ALEMBIC_INI.read_text()

    assert "postgresql" not in text
    assert "sqlalchemy.url =" not in text


def test_the_baseline_is_the_root_of_the_chain(env: dict[str, str]) -> None:
    """Every revision hangs, transitively, from this one — that is what a baseline is."""
    script = ScriptDirectory.from_config(alembic_config(Settings()))

    assert script.get_base() == BASELINE_REVISION
    assert script.get_revision(BASELINE_REVISION).down_revision is None


def test_the_migration_tree_has_exactly_one_head(env: dict[str, str]) -> None:
    """Two heads mean two branches reached main; `alembic upgrade head` then fails opaquely."""
    config = alembic_config(Settings())

    assert len(ScriptDirectory.from_config(config).get_heads()) == 1


def test_head_revision_reports_the_tree_head(env: dict[str, str]) -> None:
    config = alembic_config(Settings())

    assert head_revision(config) == ScriptDirectory.from_config(config).get_heads()[0]


def test_multiple_heads_are_named_rather_than_raised_opaquely(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`get_current_head()` raises `MultipleHeads` from inside Alembic before any check
    here could run; `get_heads()` lets the failure name the branches at start-up."""
    monkeypatch.setattr(ScriptDirectory, "get_heads", lambda self: ["0009_left", "0009_right"])

    with pytest.raises(RuntimeError, match="0009_left, 0009_right"):
        head_revision(alembic_config(Settings()))


def test_a_tree_with_no_head_is_named_too(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ScriptDirectory, "get_heads", lambda self: [])

    with pytest.raises(RuntimeError, match="exactly one head"):
        head_revision(alembic_config(Settings()))


def test_the_baseline_revision_applies_no_schema_change(env: dict[str, str]) -> None:
    """A domain table belongs to the story that needs it, not to the foundation.

    Scoped to the baseline file, which is why it keeps holding: revisions are append-only,
    so a later story adds a file beside this one and never edits it.
    """
    tree = ast.parse((VERSIONS / "0001_baseline.py").read_text())
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}

    assert set(functions) == {"upgrade", "downgrade"}
    for name, function in functions.items():
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
        assert calls == [], f"{name}() performs {len(calls)} operation(s)"


def test_alembic_manages_the_public_schema_only(env: dict[str, str]) -> None:
    """Schema `dbos` belongs to the durable engine; Alembic must not version it (AD-6)."""
    config = alembic_config(Settings())

    assert config.get_main_option("version_table_schema") == "public"


def test_the_configuration_points_at_the_committed_script_directory(env: dict[str, str]) -> None:
    config = alembic_config(Settings())

    assert (
        Path(config.get_main_option("script_location")).resolve()
        == (BACKEND_ROOT / "alembic").resolve()
    )


def test_the_settings_are_handed_to_env_py_rather_than_re_read(env: dict[str, str]) -> None:
    """`env.py` takes the `Settings` the process already built (AD-20)."""
    settings = Settings()

    config = alembic_config(settings)

    assert config.attributes["settings"] is settings


def test_the_configured_paths_are_split_into_real_entries(env: dict[str, str]) -> None:
    """`path_separator` decides how `prepend_sys_path` is split.

    With `os` the separator is `:` on this platform, so `. src` stays one string and
    neither entry ever reaches `sys.path` — the setting silently does nothing.
    """
    config = alembic_config(Settings())

    assert config.get_prepend_sys_paths_list() == [".", "src"]


# ── the template every future revision is generated from ─────────────────────


def _ruff() -> str | None:
    """Console scripts sit beside the interpreter in a venv, but not on every platform."""
    beside = Path(sys.executable).parent / "ruff"
    for candidate in (beside, beside.with_suffix(".exe")):
        if candidate.exists():
            return str(candidate)
    return shutil.which("ruff")


RUFF = _ruff()


def _run_ruff(*args: str) -> subprocess.CompletedProcess[str]:
    assert RUFF is not None
    return subprocess.run(  # fixed argv, no shell
        [RUFF, *args],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def generated_revision(tmp_path: Path, env: dict[str, str]) -> Path:
    """A revision generated from the committed template, into a throwaway tree.

    Two are generated: the first has no parent, the second has one, so both branches of the
    template's `Revises:` line are covered.
    """
    script_location = tmp_path / "alembic"
    (script_location / "versions").mkdir(parents=True)
    for name in ("env.py", "script.py.mako"):
        shutil.copy(BACKEND_ROOT / "alembic" / name, script_location / name)

    config = Config()
    config.set_main_option("script_location", str(script_location))
    command.revision(config, message="first probe")
    command.revision(config, message="second probe")

    return script_location / "versions"


@pytest.mark.skipif(RUFF is None, reason="ruff not installed")
def test_a_generated_revision_passes_the_lint_gate(generated_revision: Path) -> None:
    """Otherwise every future migration lands red on `make lint` and its story pays for it."""
    result = _run_ruff("check", str(generated_revision))

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(RUFF is None, reason="ruff not installed")
def test_a_generated_revision_is_already_formatted(generated_revision: Path) -> None:
    result = _run_ruff("format", "--check", str(generated_revision))

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_revision_with_operations_also_passes_the_lint_gate(tmp_path: Path) -> None:
    """The generated-above case has no operations, so `op`/`sa` are not even imported.

    Autogenerate needs a database, so the operations branch is rendered directly from the
    committed template instead.
    """
    if RUFF is None:  # pragma: no cover — ruff is a declared dev dependency
        pytest.skip("ruff not installed")

    rendered = Template(filename=str(BACKEND_ROOT / "alembic" / "script.py.mako")).render(
        message="add the project table",
        up_revision="0002_project",
        down_revision=BASELINE_REVISION,
        create_date="2026-09-04 10:00:00.000000",
        branch_labels=None,
        depends_on=None,
        imports="",
        upgrades='op.create_table(\n        "project",\n        sa.Column("id", sa.Uuid()),\n    )',
        downgrades='op.drop_table("project")',
        comma=lambda value: value if isinstance(value, str) else ", ".join(value or []),
        n=lambda value: value,
    )
    target = tmp_path / "0002_project.py"
    target.write_text(rendered)

    assert _run_ruff("check", str(target)).returncode == 0, _run_ruff("check", str(target)).stdout
    assert _run_ruff("format", "--check", str(target)).returncode == 0


# ── running them ─────────────────────────────────────────────────────────────


class _Recorder:
    def __init__(self) -> None:
        self.order: list[str] = []


@pytest.fixture
def recorder() -> _Recorder:
    return _Recorder()


def test_run_migrations_upgrades_to_head_and_returns_the_revision(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, recorder: _Recorder
) -> None:
    upgrades: list[str] = []

    def fake_upgrade(config: Any, revision: str) -> None:
        recorder.order.append("upgrade")
        upgrades.append(revision)

    monkeypatch.setattr(migrations.command, "upgrade", fake_upgrade)

    head = run_migrations(Settings())

    assert upgrades == ["head"]
    assert head == ScriptDirectory.from_config(alembic_config(Settings())).get_heads()[0]


def test_run_migrations_logs_the_line_the_operator_looks_for(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(migrations.command, "upgrade", lambda config, revision: None)
    configure_logging("info")

    run_migrations(Settings())

    out = capsys.readouterr().out
    assert "migrations applied" in out
    assert ScriptDirectory.from_config(alembic_config(Settings())).get_heads()[0] in out


def test_a_failed_upgrade_aborts_rather_than_serving_a_half_migrated_schema(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def exploding_upgrade(config: Any, revision: str) -> None:
        raise RuntimeError("relation already exists")

    monkeypatch.setattr(migrations.command, "upgrade", exploding_upgrade)

    with pytest.raises(RuntimeError, match="relation already exists"):
        run_migrations(Settings())


# ── the ordering inside main() ───────────────────────────────────────────────


def _run_lifespan(app: Any, order: list[str]) -> None:
    """Drive the application's start-up the way uvicorn does, then note the bind."""

    async def start() -> None:
        async with app.router.lifespan_context(app):
            order.append("bind")

    asyncio.run(start())


def test_main_migrates_before_the_socket_is_bound(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, recorder: _Recorder
) -> None:
    def fake_migrate(settings: Settings) -> str:
        recorder.order.append("migrate")
        return BASELINE_REVISION

    def fake_run(app: Any, **kwargs: Any) -> None:
        _run_lifespan(app, recorder.order)

    monkeypatch.setattr(main_module, "run_migrations", fake_migrate)
    monkeypatch.setattr(main_module.uvicorn, "run", fake_run)

    main_module.main()

    assert recorder.order == ["migrate", "bind"]


def test_a_failed_migration_stops_the_process_before_it_serves(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, recorder: _Recorder
) -> None:
    """The process must never serve a half-migrated schema."""

    def exploding_migrate(settings: Settings) -> str:
        raise RuntimeError("relation already exists")

    def fake_run(app: Any, **kwargs: Any) -> None:
        _run_lifespan(app, recorder.order)

    monkeypatch.setattr(main_module, "run_migrations", exploding_migrate)
    monkeypatch.setattr(main_module.uvicorn, "run", fake_run)

    with pytest.raises(RuntimeError, match="relation already exists"):
        main_module.main()

    assert "bind" not in recorder.order


def test_main_hands_uvicorn_an_application_that_migrates(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wiring is `main()`'s, so a test-built application carries no start-up step."""
    captured: dict[str, Any] = {}
    monkeypatch.setattr(main_module.uvicorn, "run", lambda app, **kw: captured.update(app=app))
    monkeypatch.setattr(main_module, "run_migrations", lambda settings: BASELINE_REVISION)

    main_module.main()

    served = captured["app"]
    plain = main_module.create_app(Settings())

    assert served.router.lifespan_context is not plain.router.lifespan_context


def test_a_test_built_application_runs_no_migration(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, recorder: _Recorder
) -> None:
    """`create_app(settings)` is the shape every unit test builds: no database, ever."""
    monkeypatch.setattr(migrations.command, "upgrade", _refuse)

    _run_lifespan(create_app(Settings()), recorder.order)

    assert recorder.order == ["bind"]


def _refuse(*args: Any, **kwargs: Any) -> None:
    pytest.fail("no unit test may reach the database")


def test_building_the_application_needs_no_database(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`create_app` performs no I/O — that is why the unit suite can build it at all."""
    monkeypatch.setattr(migrations.command, "upgrade", _refuse)

    assert create_app(Settings()) is not None
