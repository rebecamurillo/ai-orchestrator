"""`domain/ports/pull_requests.py` and its shared fake (epic 9 story 1)."""

from __future__ import annotations

from orchestrator.domain.ports.pull_requests import PullRequests
from tests.unit.fakes.pull_requests import FakePullRequests


def test_the_fake_satisfies_the_port() -> None:
    assert isinstance(FakePullRequests(), PullRequests)


def test_the_fake_answers_true_false_and_none_and_records_calls() -> None:
    fake = FakePullRequests({("o", "a", "f"): True}, unreadable=[("o", "u", "f")])

    assert fake.merged("o", "a", "f") is True
    assert fake.merged("o", "b", "f") is False
    assert fake.merged("o", "u", "f") is None
    assert fake.calls == [("o", "a", "f"), ("o", "b", "f"), ("o", "u", "f")]
