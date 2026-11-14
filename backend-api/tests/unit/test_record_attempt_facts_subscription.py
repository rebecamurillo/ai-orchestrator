"""`fact_set.subscription` is written once at attempt end and unknown elsewhere (AC10)."""

from __future__ import annotations

from dataclasses import fields, replace
from typing import Any

import pytest

from orchestrator.application.use_cases.calculate_metrics import CalculationPorts
from orchestrator.application.use_cases.record_attempt_facts import FactsPorts, record_attempt_facts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.writers import open_facts_ports
from orchestrator.infrastructure.dbos.startup import walker_deps
from orchestrator.infrastructure.facts_jobs import facts_jobs
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.log_facts import ScriptedLogFacts, facts_ports

LOG = "/work/logs/1.log"


def an_ended(harness: str) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=new_id(),
        step_run_id=new_id(),
        n=1,
        status="done",
        harness=harness,
        log_path=LOG,
    )


def stored_subscription(harness: str, setting: bool | None) -> bool | None:
    extractors: Any = {harness: ScriptedLogFacts()}
    ports = replace(facts_ports(extractors, existing=[LOG]), subscription_auth=setting)
    stored = record_attempt_facts(ports, an_ended(harness))
    assert stored is not None
    return stored.subscription


@pytest.mark.parametrize(
    ("harness", "setting", "expected"),
    [
        ("claude", True, True),
        ("codex", True, False),
        ("claude", False, False),
        ("opencode", False, False),
        ("claude", None, None),
        ("codex", None, None),
    ],
)
def test_the_value_follows_the_harness_and_the_setting(
    harness: str, setting: bool | None, expected: bool | None
) -> None:
    assert stored_subscription(harness, setting) is expected


def test_the_default_of_the_ports_is_unknown() -> None:
    ports = facts_ports({"fake": ScriptedLogFacts()}, existing=[LOG])
    assert ports.subscription_auth is None


class Session:
    def close(self) -> None:
        pass


@pytest.mark.parametrize("setting", [True, False, None])
def test_open_facts_ports_passes_the_value_through(setting: bool | None) -> None:
    with open_facts_ports(Session, {}, subscription_auth=setting) as ports:  # type: ignore[arg-type, return-value]
        assert isinstance(ports, FactsPorts)
        assert ports.subscription_auth is setting


def test_open_facts_ports_defaults_to_unknown() -> None:
    with open_facts_ports(Session, {}) as ports:  # type: ignore[arg-type, return-value]
        assert ports.subscription_auth is None


def test_the_sweep_passes_unknown(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []

    def fake_open(*_args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs["subscription_auth"])
        raise RuntimeError("stop")

    monkeypatch.setattr("orchestrator.infrastructure.facts_jobs.open_facts_ports", fake_open)
    [(_name, _cron, job)] = facts_jobs(Settings(), Session)  # type: ignore[arg-type, return-value]
    with pytest.raises(RuntimeError):
        job()
    assert seen == [None]


@pytest.mark.parametrize("setting", [True, False])
def test_the_attempt_end_scope_carries_the_setting(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, setting: bool
) -> None:
    monkeypatch.setenv("CLAUDE_SUBSCRIPTION_AUTH", "true" if setting else "false")
    settings = Settings()
    deps = walker_deps(settings, Session, FakeGit())  # type: ignore[arg-type, return-value]
    scope = deps.step_ports.facts_writes
    assert scope is not None
    with scope() as ports:
        assert ports.subscription_auth is setting


def test_the_recalculation_passes_unknown() -> None:
    claude = replace(facts_ports({}, existing=[]), subscription_auth=True)
    given = {f.name: None for f in fields(CalculationPorts)}
    given |= {"fact_sets": claude.facts, "uow": claude.uow, "clock": claude.clock}
    given |= {"extractors": {}, "log_exists": claude.log_exists}
    ports = CalculationPorts(**given).facts_ports()

    assert ports.subscription_auth is None
