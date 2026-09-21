"""Pre-rendering the workflow snapshot before an agent is dispatched (AD-9, FR-14).

The behaviour these tests pin was declared by the Operator on 2026-09-21, from the six
`007-*.log` transcripts of run `01a0bf7c-2fdc-714c-a7ee-92a3b0429395`: the agent was asked
by `SKILL.md` to substitute two placeholders into a `render_skill.py` command, run it and
follow the path it printed, and a 30B harness failed that hand-off in all six attempts —
inventing CLI arguments the renderer does not take, or never running it at all — and then
improvised the story instead of halting. The orchestrator renders the snapshot itself and
hands the agent the resolved path, so the hand-off cannot be fumbled.

Skipping is not failing: a repository with no renderer dispatches exactly as it did before,
which is what keeps this change safe for targets that never ran `repo-init`.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.steps import agent_render
from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.domain.ports.process import Outcome
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import (
    HEAD_SHA,
    SKILL,
    World,
    a_world,
    resolved,
)
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.process import FakeProcessRunner

#: A second sha, so `execute` sees HEAD move between `mark_started` and `mark_finished`.
END_SHA = "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d"

#: Where the claude adapter installs its skills; `scripts/harness/claude.sh` writes the same.
SKILLS_DIR = Path("/home/agent/.claude/skills")
#: The path a successful render prints, under the worktree's own self-ignoring `_bmad/render`.
SNAPSHOT = "/work/acme/widgets/wt/feat-x/_bmad/render/bmad-build-auto/acme-1a2b/3c4d/workflow.md"
#: The renderer's own success line, verbatim (`render_skill.py` `main`).
FOLLOW_LINE = f"read and follow {SNAPSHOT}\n"
#: The log the render writes, relative to its own directory — what the fake is keyed by.
RENDER_LOG = "003-1.log.render"
#: The renderer, where `bmad.install` leaves it in the worktree (AD-16).
SCRIPT = "_bmad/scripts/render_skill.py"


def a_render_world(
    *,
    output: str = FOLLOW_LINE,
    outcome: Outcome | None = None,
    skills_dir: Path | None = SKILLS_DIR,
    script: bool = True,
    **over: object,
) -> World:
    """A world whose worktree holds the renderer and whose render log holds `output`."""
    files = {RENDER_LOG: output}
    if script:
        files[SCRIPT] = "# the renderer"
    process = FakeProcessRunner(default=outcome) if outcome is not None else FakeProcessRunner()
    return a_world(
        files=files,
        process=process,
        harness=FakeHarness(skills_dir=skills_dir),
        **over,  # type: ignore[arg-type]
    )


def prerender(world: World) -> str | StepResult | None:
    return agent_render.prerendered_workflow(world.ctx, world.harness)


# ── the command, and the line it answers with ────────────────────────────────


def test_the_command_names_the_worktree_as_project_root_and_the_harness_skill_directory() -> None:
    argv = agent_render.render_argv(Path("/wt"), SKILLS_DIR / SKILL)

    assert argv == [
        "uv",
        "run",
        "--no-cache",
        "/wt/_bmad/scripts/render_skill.py",
        "--project-root",
        "/wt",
        "--skill",
        f"{SKILLS_DIR / SKILL}",
    ]


def test_no_argument_carries_the_dispatch_facts_the_renderer_has_no_parameter_for() -> None:
    """Attempts 3 and 6 appended `--spec-folder`/`--story-id` and argparse rejected both."""
    argv = agent_render.render_argv(Path("/wt"), SKILLS_DIR / SKILL)

    assert not any(part.startswith("--") and part not in agent_render.ACCEPTED for part in argv)


def test_the_snapshot_is_read_off_the_renderers_own_success_line() -> None:
    assert agent_render.snapshot_from(FOLLOW_LINE) == SNAPSHOT


def test_a_second_render_of_the_same_sources_answers_with_the_line_it_appended_last() -> None:
    """The log is appended to, so an idempotent re-render leaves two lines and the last wins."""
    doubled = FOLLOW_LINE + "read and follow /wt/_bmad/render/later/workflow.md\n"

    assert agent_render.snapshot_from(doubled) == "/wt/_bmad/render/later/workflow.md"


def test_output_with_no_success_line_yields_no_snapshot() -> None:
    assert agent_render.snapshot_from("HALT: project root does not contain _bmad/\n") is None


# ── when the render runs, and what the caller gets back ──────────────────────


def test_a_skill_dispatch_renders_the_snapshot_and_answers_with_its_path() -> None:
    world = a_render_world()

    assert prerender(world) == SNAPSHOT


def test_the_render_runs_in_the_worktree_with_none_of_this_process_environment() -> None:
    """AD-5: the renderer is a child process and receives no credential of this instance."""
    world = a_render_world()

    prerender(world)

    started = world.process.called("start")[0]
    assert started["cwd"] == Path(world.ctx.cwd or "")
    assert started["env"] == {}


def test_the_render_writes_beside_the_attempts_own_log_and_not_over_it() -> None:
    world = a_render_world()

    prerender(world)

    assert world.process.called("start")[0]["log_path"] == Path(
        f"/work/logs/{world.attempt.run_id}/003-1.log.render"
    )


# ── the three forms that render nothing at all ───────────────────────────────


def test_a_row_carrying_a_literal_prompt_names_no_skill_and_renders_nothing() -> None:
    world = a_render_world(with_resolved=resolved(prompt="Do the thing."))

    assert prerender(world) is None
    assert world.process.called("start") == []


def test_a_harness_that_installs_no_skills_renders_nothing() -> None:
    world = a_render_world(skills_dir=None)

    assert prerender(world) is None
    assert world.process.called("start") == []


def test_a_worktree_without_the_renderer_dispatches_as_it_did_before() -> None:
    """A target repository that never ran `repo-init` keeps working, unrendered."""
    world = a_render_world(script=False)

    assert prerender(world) is None
    assert world.process.called("start") == []


# ── a renderer that is there and fails is loud (hard rule 7) ─────────────────


def test_a_failing_render_parks_the_run_rather_than_letting_the_agent_improvise() -> None:
    world = a_render_world(
        output="HALT: project root does not contain _bmad/: /wt\n",
        outcome=Outcome(exit_code=1, timed_out=False),
    )

    parked = prerender(world)

    assert isinstance(parked, StepResult)
    assert parked.status == "error"
    assert parked.park is not None
    assert parked.park.kind == "misconfigured"
    assert "project root does not contain _bmad/" in parked.park.reason


def test_a_render_killed_by_its_own_deadline_parks_and_says_so() -> None:
    world = a_render_world(outcome=Outcome(exit_code=None, timed_out=True))

    parked = prerender(world)

    assert isinstance(parked, StepResult)
    assert parked.park is not None
    assert "timeout" in parked.park.reason


def test_a_render_that_exits_clean_but_prints_no_path_parks_too() -> None:
    """Exit 0 with nothing to follow is the silent success attempt 6 acted on. Never again."""
    world = a_render_world(output="")

    parked = prerender(world)

    assert isinstance(parked, StepResult)
    assert parked.park is not None
    assert parked.park.kind == "misconfigured"


def test_a_park_names_the_row_so_the_operator_opens_the_step_that_failed() -> None:
    world = a_render_world(outcome=Outcome(exit_code=2, timed_out=False))

    parked = prerender(world)

    assert isinstance(parked, StepResult)
    assert parked.park is not None
    assert parked.park.path == world.row.path


# ── what the harness is actually asked, end to end ───────────────────────────


def dispatched(**over: object) -> World:
    """A render world whose HEAD moves, so `AgentExecutor.execute` runs to a dispatch."""
    return a_render_world(git=FakeGit(status=[""], head_sha=[HEAD_SHA, END_SHA]), **over)


def test_the_dispatched_prompt_hands_the_agent_the_rendered_path_and_forbids_the_renderer() -> None:
    world = dispatched()

    AgentExecutor().execute(world.ctx)

    prompt = world.harness.calls[0]["prompt"]
    assert SNAPSHOT in prompt
    assert "Do not run render_skill.py yourself" in prompt


def test_the_dispatch_sentence_still_carries_the_folder_and_id_the_workflow_reads() -> None:
    """Step 01 of the workflow resolves the story from this sentence, so it must survive."""
    world = dispatched()

    AgentExecutor().execute(world.ctx)

    assert "in folder+id dispatch mode" in world.harness.calls[0]["prompt"]


def test_a_row_that_rendered_nothing_is_dispatched_exactly_as_it_was_before() -> None:
    world = dispatched(script=False)

    AgentExecutor().execute(world.ctx)

    prompt = world.harness.calls[0]["prompt"]
    assert prompt.startswith("Run the skill")
    assert "already rendered" not in prompt


def test_a_failed_render_parks_before_the_attempt_starts_so_none_is_left_open() -> None:
    """The park comes out of `execute` itself: no harness ran and no attempt was started."""
    world = dispatched(outcome=Outcome(exit_code=1, timed_out=False))

    result = AgentExecutor().execute(world.ctx)

    assert result.status == "error"
    assert result.park is not None
    assert world.harness.calls == []
    assert not [call for call in world.attempts.calls if call[0] == "mark_started"]
