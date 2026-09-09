"""`handle_signal` (SPEC CAP-9, FR-20, AD-13): the scope gate over `signal_run`, and the
`cancel` cleanup `signal_run` cannot reach.

Every kind's own AD-13 semantics — which rows move, what the Run reads afterwards — is
`signal_effects.py`'s and `rules/signals.py`'s own coverage (`test_signal_run.py`,
`test_signal_rules.py`, 4.5). This module proves two things instead: that `cancel`, `retry`
and `continue` on a `checkpoint` or `plan_stale` park reach the real effect exactly as 4.5
built it; and that every other kind — admitted by AD-13 but not yet built by this epic — is
refused with `"{kind} not available yet"` rather than silently applying.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from orchestrator.application.steps.context import RunEnvironment
from orchestrator.application.use_cases.signals import (
    SignalEffectPorts,
    handle_signal,
)
from orchestrator.domain.errors import Conflict
from orchestrator.domain.values import Signal, Worktree
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
COMMIT_GUARD = "stories[0].commit-guard"
CHECKPOINT_ROW = "stories[1].after"
WORK_DIR = "/work"


def parked(
    park_kind: str, park_path: str, row_status: str, plan: object = EPIC_PLAN, **over: object
) -> World:
    """A Run stopped for the Operator on one row — `test_signal_run.py`'s own shape."""
    return a_world(
        "needs_you",
        plan,  # type: ignore[arg-type]
        {park_path: row_status},
        park_kind=park_kind,
        park_path=park_path,
        park_reason="why it stopped",
        **over,
    )


def a_run_environment(run_id: UUID) -> RunEnvironment:
    return RunEnvironment(
        run_id=run_id,
        project_slug="acme",
        repository_slug="widget",
        repository_url="https://github.com/acme/widget",
        default_branch="main",
        install_command="",
        bmad_version="1.0.0",
        spec_folder=None,
    )


#: Distinguishes "no environment kwarg supplied" from "supplied, and it is `None`".
_DEFAULT_ENV = object()


def effect_ports(
    world: World,
    *,
    git: FakeGit | None = None,
    process: FakeProcessRunner | None = None,
    env: RunEnvironment | object | None = _DEFAULT_ENV,
) -> SignalEffectPorts:
    resolved_env = a_run_environment(world.run.id) if env is _DEFAULT_ENV else env
    return SignalEffectPorts(
        signal=world.signal_ports,
        git=git if git is not None else FakeGit(),
        process=process if process is not None else FakeProcessRunner(),
        work_dir=WORK_DIR,
        read_environment=lambda _run_id: resolved_env,
    )


def send(world: World, ports: SignalEffectPorts, kind: str, **payload: object) -> object:
    return handle_signal(ports, world.run.id, Signal(kind=kind, payload=payload))


# ── in scope: cancel, retry, continue on checkpoint / plan_stale ────────────────────────


def test_cancel_kills_live_processes_and_cleans_up_created_unpushed_worktrees() -> None:
    world = a_world("running", EPIC_PLAN, {BUILD: "running"})
    attempt = an_attempt(world, BUILD, pgid=4321)
    assert attempt.ended_at is None
    worktree = Worktree(
        branch="chore/x", path="/work/wt/chore-x", created_branch=True, pushed=False
    )
    world.ports.runs.update(world.run.model_copy(update={"worktrees": (worktree,)}))
    git = FakeGit()
    process = FakeProcessRunner()
    ports = effect_ports(world, git=git, process=process)

    outcome = send(world, ports, "cancel", confirm=True)

    assert outcome.run.status == "cancelled"
    assert [call["pgid"] for call in process.called("kill_group")] == [4321]
    base = a_run_environment(world.run.id).base_dir(WORK_DIR)
    assert git.called("remove_worktree") == [(base, Path(worktree.path))]
    assert git.called("delete_branch") == [(base, "chore/x")]


def test_cancel_leaves_a_pushed_branch_and_a_branch_it_did_not_create() -> None:
    world = a_world("running", EPIC_PLAN, {})
    pushed = Worktree(
        branch="chore/pushed", path="/work/wt/pushed", created_branch=True, pushed=True
    )
    existing = Worktree(branch="main", path="/work/wt/main", created_branch=False, pushed=False)
    world.ports.runs.update(world.run.model_copy(update={"worktrees": (pushed, existing)}))
    git = FakeGit()
    process = FakeProcessRunner()
    ports = effect_ports(world, git=git, process=process)

    send(world, ports, "cancel", confirm=True)

    assert process.called("kill_group") == []
    base = a_run_environment(world.run.id).base_dir(WORK_DIR)
    assert git.called("remove_worktree") == [
        (base, Path(pushed.path)),
        (base, Path(existing.path)),
    ]
    assert git.called("delete_branch") == []


def test_cancel_with_no_worktrees_touches_no_git_command() -> None:
    world = a_world("running", EPIC_PLAN, {})
    git = FakeGit()
    ports = effect_ports(world, git=git)

    send(world, ports, "cancel", confirm=True)

    assert git.called("remove_worktree") == []
    assert git.called("delete_branch") == []


def test_cancel_without_a_resolved_environment_still_kills_processes() -> None:
    """A Repository deleted underneath the Run: no `RunEnvironment`, no git call — but the
    live process is still killed (AD-13's own idempotence, not a reason to leave it)."""
    world = a_world("running", EPIC_PLAN, {BUILD: "running"})
    an_attempt(world, BUILD, pgid=99)
    git = FakeGit()
    process = FakeProcessRunner()
    ports = effect_ports(world, git=git, process=process, env=None)

    send(world, ports, "cancel", confirm=True)

    assert [call["pgid"] for call in process.called("kill_group")] == [99]
    assert git.called("remove_worktree") == []


def test_retry_re_queues_the_errored_row() -> None:
    world = parked("push_rejected", "push", "error")
    ports = effect_ports(world)

    outcome = send(world, ports, "retry")

    assert world.status_of("push") == "queued"
    assert outcome.run.status == "running"
    assert ("signal", world.run.id) in [(name, args[0]) for name, args in world.engine.calls]


def test_continue_finishes_a_checkpoint_row_and_queues_its_successor() -> None:
    world = parked("checkpoint", CHECKPOINT_ROW, "checkpoint")
    ports = effect_ports(world)

    outcome = send(world, ports, "continue")

    assert world.status_of(CHECKPOINT_ROW) == "done"
    assert world.status_of("push") == "queued"
    assert outcome.run.status == "running"


def test_continue_on_plan_stale_resumes_the_row_itself() -> None:
    world = parked("plan_stale", "plan", "error")
    ports = effect_ports(world)

    outcome = send(world, ports, "continue")

    assert world.status_of("plan") == "running"
    assert outcome.run.status == "running"


# ── out of scope: refused after `validate` passes, nothing written ──────────────────────


def test_continue_on_protected_path_is_refused_not_available_yet() -> None:
    world = parked("protected_path", COMMIT_GUARD, "error")
    ports = effect_ports(world)

    with pytest.raises(Conflict, match="continue not available yet"):
        send(world, ports, "continue")

    assert world.status_of(COMMIT_GUARD) == "error"
    assert world.engine.calls == []


def test_answer_moves_the_blocked_row_and_resumes_the_run() -> None:
    """`answer` was refused here until SPEC CAP-1 (6.1) built the `agent` row's own resume —
    the archive, the re-dispatch and the prompt clause. It is in scope from that story on:
    the blocked row goes back to `queued` and the Run leaves `needs_you`, which is FR-18's
    "the Run leaves `needs_you` as soon as `signal_run` commits"."""
    world = parked("blocked", BUILD, "blocked")
    ports = effect_ports(world)

    outcome = send(world, ports, "answer", text="use the psycopg adapter")

    assert world.status_of(BUILD) == "queued"
    assert outcome.run.status == "running"


def _terminal_release_world() -> World:
    return parked("misconfigured", "push", "error", terminal_session=True)


def _terminal_resume_world() -> World:
    return parked("blocked", BUILD, "blocked", terminal_session=True)


@pytest.mark.parametrize(
    ("world_factory", "kind", "payload"),
    [
        (lambda: parked("budget", BUILD, "blocked"), "budget_raise", {"budget_usd": "50"}),
        (lambda: parked("misconfigured", "push", "error"), "terminal_start", {}),
        (_terminal_release_world, "terminal_release", {}),
        (_terminal_resume_world, "terminal_resume", {}),
    ],
    ids=[
        "budget_raise",
        "terminal_start",
        "terminal_release",
        "terminal_resume",
    ],
)
def test_every_kind_outside_this_epics_scope_is_refused_not_available_yet(
    world_factory: object, kind: str, payload: dict[str, object]
) -> None:
    world = world_factory()  # type: ignore[operator]
    ports = effect_ports(world)

    with pytest.raises(Conflict, match=f"{kind} not available yet"):
        send(world, ports, kind, **payload)

    assert world.engine.calls == []


def test_a_signal_ad13_itself_refuses_keeps_ad13s_own_refusal_text() -> None:
    """A genuinely inadmissible signal — `answer` on a `running` Run — never reaches this
    module's own refusal: `validate` raises first, with AD-13's own sentence."""
    world = a_world("running", EPIC_PLAN, {})
    ports = effect_ports(world)

    with pytest.raises(Conflict, match="signal answer invalid for status running"):
        send(world, ports, "answer", text="anything")
