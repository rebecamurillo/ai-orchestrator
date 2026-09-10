"""AD-17 at the tail, over a dispatch the Template sent to write an anchor.

`test_agent_protected_paths.py` settles the check itself: the range it reads, the park it
raises, and the Operator's *Accept*. What is settled here is the one thing a Template can say
before any of that happens — `writes`, on the `agent` step — and it is asserted through the
executor rather than through the rule, because the row is where the declaration has to
survive to: planned once (AD-7), read at the tail, and never re-derived from the skill name.

`repo-init@1`'s `context` step is the shipped case. It runs `bmad-project-context`, whose
only output is the repository's `AGENTS.md` — a file `rules/protected_paths.py` protects by
basename, wherever it is and whether or not it exists yet. Without the declaration every Run
of that Template would park on the file the Operator asked for.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.steps.agent_tail import PROTECTED
from orchestrator.application.templates.table import WRITES_KEY
from orchestrator.domain.ports.git import Change
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import HEAD_SHA, World
from tests.unit.application.steps.agent_tail_fixtures import (
    END_SHA,
    LOG_PATH,
    a_tail_world,
    contracted,
)
from tests.unit.fakes.git import FakeGit

AGENTS = "AGENTS.md"
NESTED_AGENTS = "web-client/AGENTS.md"
SPEC_FOLDER = "specs/notifications"
SPEC_MD = f"{SPEC_FOLDER}/SPEC.md"
ANCHORS = frozenset({SPEC_MD})


def a_git(*changes: Change, status: str = "") -> FakeGit:
    return FakeGit(status=[status], head_sha=[HEAD_SHA, END_SHA], diff_changes=[tuple(changes)])


def a_world(*, writes: list[str] | None = None, **over: Any) -> World:
    """A tail world whose row declares `writes`, over a walker that resolved the anchors."""
    extras: dict[str, Any] = {} if writes is None else {WRITES_KEY: writes}
    world = a_tail_world(with_resolved=contracted(**extras), **over)
    environment = world.ctx.ports.run_env
    assert environment is not None
    world.ctx = replace(
        world.ctx,
        ports=replace(world.ctx.ports, run_env=replace(environment, anchors=ANCHORS)),
    )
    return world


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


# ── the declaration, honoured ───────────────────────────────────────────────


def test_a_declared_agents_file_the_dispatch_wrote_is_not_a_hit() -> None:
    world = a_world(writes=[AGENTS], git=a_git(Change(path=AGENTS, kind="added")))

    assert run(world) == StepResult(status="done", gate="liveness", output_ref=str(LOG_PATH))


def test_a_declared_file_left_uncommitted_is_not_a_hit_either() -> None:
    """The tail unions the range with the tree, so both readings need the declaration."""
    world = a_world(writes=[AGENTS], git=a_git(status=f"?? {AGENTS}\n"))

    result = run(world)

    assert result.park is None
    assert result.status == "done"


def test_the_story_file_is_still_routed_on_once_the_declaration_clears_the_check() -> None:
    """FR-31 puts the check in front of the routing; clearing it hands the row back."""
    world = a_world(writes=[AGENTS], git=a_git(Change(path=AGENTS, kind="modified")))

    assert run(world).status == "done"


# ── the declaration, and what it does not cover ─────────────────────────────


def test_an_undeclared_agents_file_is_the_hit_it_always_was() -> None:
    world = a_world(git=a_git(Change(path=AGENTS, kind="added")))

    result = run(world)

    assert result.status == "error"
    assert result.reason == PROTECTED.format(paths=AGENTS)


def test_declaring_one_agents_file_does_not_license_another() -> None:
    world = a_world(writes=[AGENTS], git=a_git(Change(path=NESTED_AGENTS, kind="added")))

    result = run(world)

    assert result.reason == PROTECTED.format(paths=NESTED_AGENTS)


def test_an_anchor_the_dispatch_was_not_sent_to_still_parks_the_run() -> None:
    world = a_world(writes=[AGENTS], git=a_git(Change(path=SPEC_MD, kind="modified")))

    result = run(world)

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "protected_path"
    assert result.reason == PROTECTED.format(paths=SPEC_MD)


def test_only_the_undeclared_anchor_is_named_when_both_changed() -> None:
    world = a_world(
        writes=[AGENTS],
        git=a_git(Change(path=AGENTS, kind="added"), Change(path=SPEC_MD, kind="modified")),
    )

    assert run(world).reason == PROTECTED.format(paths=SPEC_MD)
