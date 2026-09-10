"""The sixth reason a Run has no terminal: the adapter itself answers no line (FR-21, 7.3).

`Harness.resume_command` returns `str | None` from this story on, because `local` has no resume
form at all — `opencode run` opens a session and nothing in this system continues one. The read
model already turns that harness away one step earlier, on `capabilities.resume`, so this is the
same answer stated twice; what it buys is that the *second* statement is the adapter's own.

That matters for a specific failure. `capabilities.resume` is a claim an adapter makes about
itself, and a harness that claimed it and then could not produce a line would otherwise have its
`None` interpolated into a `docker compose exec … sh -c 'cd /work && None'` — a command an
Operator would paste and watch fail, for a session that was never resumable. `terminal: null` is
the honest answer, and it is the one the Run detail already knows how to render.

`tests/unit/test_terminal_command.py` is frozen and already covers the other five cases; this is
a sibling module for the one it could not have anticipated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.application.use_cases.terminal import TerminalPorts, resume_command
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness.registry import build_terminal_env
from orchestrator.infrastructure.settings import Settings

PROJECT_SLUG = "acme"
SESSION = "ses_7f3c1a0b9d2e4f5a"
WORKTREE = "/work/acme/widgets/wt/feat-x"
STARTED_AT = datetime(2026, 9, 10, 9, 0, tzinfo=UTC)
HARNESS = "local"


class NoResumeLine:
    """A harness that claims the capability and answers no line — the case this covers.

    `local`'s real adapter answers `None` too, and declares `capabilities.resume = False` as
    well, so it never reaches this branch. Claiming the capability here is what makes the
    branch reachable at all, which is the only way to state that it is guarded.
    """

    name = HARNESS
    capabilities = type("Caps", (), {"resume": True})()

    def resume_command(self, cwd: str, session_id: str) -> str | None:
        return None


@pytest.fixture
def settings(env: dict[str, str]) -> Settings:
    return Settings()


def an_attempt() -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=new_id(),
        step_run_id=new_id(),
        n=1,
        status="blocked",
        harness=HARNESS,
        model="local-coder",
        session_id=SESSION,
        started_at=STARTED_AT,
    )


def a_run(attempt: Attempt) -> Run:
    return Run(
        id=attempt.run_id,
        project_id=new_id(),
        repository_id=new_id(),
        template_name="story",
        template_version=1,
        status="needs_you",
        budget_usd=Decimal("40"),
        created_at=STARTED_AT,
        worktree_path=WORKTREE,
    )


def a_row(attempt: Attempt) -> StepRun:
    return StepRun(
        id=attempt.step_run_id,
        run_id=attempt.run_id,
        seq=0,
        path="stories[0].build",
        label="build",
        kind="agent",
        gate="liveness",
        status="blocked",
        story_id="7-3",
    )


def test_an_adapter_that_answers_no_line_leaves_the_run_without_a_terminal(
    settings: Settings,
) -> None:
    attempt = an_attempt()
    ports = TerminalPorts(
        env=build_terminal_env(settings),
        harnesses={HARNESS: NoResumeLine()},  # type: ignore[dict-item]
    )

    assert (
        resume_command(ports, a_run(attempt), a_row(attempt), attempt, project_slug=PROJECT_SLUG)
        is None
    )


def test_the_none_is_never_interpolated_into_a_pasteable_command(settings: Settings) -> None:
    """The failure this guard exists for, stated as the thing that must not happen."""
    attempt = an_attempt()
    ports = TerminalPorts(
        env=build_terminal_env(settings),
        harnesses={HARNESS: NoResumeLine()},  # type: ignore[dict-item]
    )

    terminal = resume_command(
        ports, a_run(attempt), a_row(attempt), attempt, project_slug=PROJECT_SLUG
    )

    assert terminal is None or "None" not in terminal.command
