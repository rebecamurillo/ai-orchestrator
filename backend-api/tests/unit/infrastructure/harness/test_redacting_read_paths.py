"""A stored event path carries no instance secret (story 6 review, 2026-11-23; AD-5)."""

from __future__ import annotations

from tests.unit.fakes.clock import EPOCH
from tests.unit.fakes.log_facts import ScriptedLogFacts

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts, EventFact
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness.facts import RedactingLogFacts
from orchestrator.infrastructure.settings import Settings


def test_a_stored_read_path_carries_stars_in_place_of_an_instance_secret(
    env: dict[str, str],
) -> None:
    token = Settings().github_token.get_secret_value()
    assert token
    events = (
        EventFact(at=EPOCH, conversation="main", kind="read", path=f"/tmp/{token}.txt"),
        EventFact(at=EPOCH, conversation="main", kind="write", path="a.py"),
        EventFact(at=EPOCH, conversation="main", kind="test_run"),
    )
    wrapped = RedactingLogFacts(ScriptedLogFacts(AttemptFacts(events=events)), (token,))
    attempt = Attempt(id=new_id(), run_id=new_id(), step_run_id=new_id(), n=1, status="done")

    facts = wrapped.extract(attempt, "/x.log")

    assert [e.path for e in facts.events] == ["/tmp/***.txt", "a.py", None]
