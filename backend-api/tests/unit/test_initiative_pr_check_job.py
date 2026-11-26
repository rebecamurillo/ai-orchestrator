"""The `initiative_pr_check` job fired through its wiring (epic 9 story 1, review 2026-11-26).

The use case enters its unit of work once per pass and once per write; the wiring must hand
it one that allows that, and close the session it opened on every path.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from orchestrator.infrastructure.jobs import INITIATIVE_PR_CHECK_NAME, scheduled_jobs
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.git import FakeGit


class NoRows:
    def all(self) -> list[Any]:
        return []


class ClosingSession:
    def __init__(self) -> None:
        self.closed = False
        self.rolled_back = False

    def scalars(self, _statement: Any) -> NoRows:
        return NoRows()

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def _job(session: ClosingSession) -> Callable[[], None]:
    jobs = scheduled_jobs(Settings(), lambda: session, FakeGit())
    return {name: job for name, _cron, job in jobs}[INITIATIVE_PR_CHECK_NAME]


def test_a_fire_with_no_initiatives_reads_once_and_closes_its_session(
    env: dict[str, str],
) -> None:
    session = ClosingSession()

    _job(session)()

    assert session.rolled_back
    assert session.closed


def test_a_fire_that_raises_still_closes_its_session(env: dict[str, str]) -> None:
    class Failing(ClosingSession):
        def scalars(self, _statement: Any) -> NoRows:
            raise RuntimeError("database gone")

    session = Failing()
    with pytest.raises(RuntimeError, match="database gone"):
        _job(session)()
    assert session.closed
