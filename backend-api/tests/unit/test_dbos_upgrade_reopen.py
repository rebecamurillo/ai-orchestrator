"""The start-up reopen pass after an upgrade (epic 9 story 3, AC7)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from orchestrator.infrastructure.dbos import startup as startup_module
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.dbos import FakeDurableEngine
from tests.unit.fakes.git import FakeGit
from tests.unit.test_dbos_advance import an_engine
from tests.unit.test_dbos_advance_sweep import _quiet, _writer_scope


def record(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    _quiet(monkeypatch)

    @contextmanager
    def opened(*_a: Any) -> Iterator[Any]:
        calls.append("open")
        yield type("P", (), {"uow": _writer_scope()})()

    monkeypatch.setattr(startup_module, "open_initiative_ports", opened)
    monkeypatch.setattr(startup_module, "reopen_after_upgrade", lambda _p: calls.append("reopen"))
    monkeypatch.setattr(startup_module, "sweep_advances", lambda *_a: calls.append("advances"))
    return calls


def test_the_pass_runs_once_after_the_advance_sweep(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
) -> None:
    calls = record(monkeypatch)
    engine = an_engine(FakeDurableEngine(), _writer_scope)

    with startup_module.serving(engine, session_factory=lambda: None, git=FakeGit()):  # type: ignore[arg-type]
        startup_module.dependency_startup_sweep(Settings())

    assert calls == ["advances", "open", "reopen"]


def test_it_does_not_run_without_git(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    calls = record(monkeypatch)
    engine = an_engine(FakeDurableEngine(), _writer_scope)

    with startup_module.serving(engine, session_factory=lambda: None):  # type: ignore[arg-type]
        startup_module.dependency_startup_sweep(Settings())

    assert calls == ["advances"]


def test_it_does_not_run_without_the_advance_scope(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
) -> None:
    calls = record(monkeypatch)
    engine = an_engine(FakeDurableEngine())

    with startup_module.serving(engine, session_factory=lambda: None, git=FakeGit()):  # type: ignore[arg-type]
        startup_module.dependency_startup_sweep(Settings())

    assert calls == []
