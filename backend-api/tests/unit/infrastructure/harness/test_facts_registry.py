"""The extractor registry: what it holds, and that stored commands are redacted (AD-5)."""

from __future__ import annotations

from pathlib import Path

from tests.unit.fakes.clock import EPOCH
from tests.unit.fakes.log_facts import ScriptedLogFacts

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts, EventFact
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness.facts import (
    RedactingLogFacts,
    build_log_facts,
    log_file_exists,
)
from orchestrator.infrastructure.settings import Settings


def test_the_registry_holds_the_fake_extractor_and_no_other(env: dict[str, str]) -> None:
    assert set(build_log_facts(Settings())) == {"fake"}


def test_a_stored_command_carries_stars_in_place_of_an_instance_secret(
    env: dict[str, str],
) -> None:
    settings = Settings()
    token = settings.github_token.get_secret_value()
    assert token
    event = EventFact(at=EPOCH, conversation="main", kind="write", command=f"git push {token}")
    bare = EventFact(at=EPOCH, conversation="main", kind="test_run")
    inner = ScriptedLogFacts(AttemptFacts(events=(event, bare)))
    wrapped = RedactingLogFacts(inner, (token,))
    attempt = Attempt(id=new_id(), run_id=new_id(), step_run_id=new_id(), n=1, status="done")

    facts = wrapped.extract(attempt, "/x.log")

    assert [e.command for e in facts.events] == ["git push ***", None]
    assert (wrapped.name, wrapped.version) == (inner.name, inner.version)
    assert wrapped.capabilities == inner.capabilities


def test_a_log_exists_only_while_its_file_does(tmp_path: Path) -> None:
    log = tmp_path / "a.log"
    assert not log_file_exists(str(log))
    log.write_text("x")
    assert log_file_exists(str(log))
