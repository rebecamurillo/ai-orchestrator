"""The `agent` kind's tail, end to end: what a dispatch that came back is reported as.

`test_routing_rule.py` drives the FR-16 table against the pure rule; this module drives the
same table through `AgentExecutor.execute`, so what is asserted here is the wiring the rule
cannot see — that the liveness glob is the one the row declared, that the file is read
through the `Workspace` port, that the attempt is recorded before anything routes, that the
row's gate survives every outcome, and that the two seams AD-9 puts around the routing are
in the order it puts them.
"""

from __future__ import annotations

import inspect

import pytest

from orchestrator.application.steps import agent_tail
from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import (
    ROW_PATH,
    SPEC_FOLDER,
    STORY_ID,
    World,
    resolved,
)
from tests.unit.application.steps.agent_tail_fixtures import (
    LOG_PATH,
    OTHER_PATH,
    RETRY_MAX,
    RETRY_PROMPT,
    STORY_GLOB,
    STORY_PATH,
    a_section,
    a_story,
    a_tail_world,
    contracted,
    retried,
)
from tests.unit.fakes.harness import FakeHarness

#: The seven conditions FR-16 calls configuration failures rather than questions.
CONDITIONS = (
    "no subagents",
    "no stories.yaml found",
    "story id not found in stories.yaml",
    "version-control metadata not writable",
    "no epic spec found",
    "unrecognized status in existing story file",
    "ambiguous story file match",
)


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


# ── done ─────────────────────────────────────────────────────────────────────


def test_a_done_file_and_a_clean_exit_is_the_step_done_at_its_own_gate() -> None:
    world = a_tail_world()

    result = run(world)

    assert result == StepResult(status="done", gate="liveness", output_ref=str(LOG_PATH))


def test_the_glob_the_row_declared_is_the_one_that_is_asked() -> None:
    """AD-7: `expect.files` was resolved before the Run started; the tail re-resolves nothing."""
    world = a_tail_world()

    run(world)

    assert STORY_GLOB in world.workspace.globbed


def test_a_row_that_declared_the_contract_without_a_glob_falls_back_to_the_story_file() -> None:
    world = a_tail_world(
        with_resolved=contracted(expect={"files": [], "status_in": []}),
    )

    result = run(world)

    assert result.status == "done"
    assert STORY_GLOB in world.workspace.globbed


def test_a_row_carrying_no_contract_at_all_reports_only_what_it_observed() -> None:
    """`resolved()` is a row from before `expect` existed: there is nothing to evaluate,
    and `done` here still means "observed", which is what gate `liveness` says."""
    world = a_tail_world(story=None, with_resolved=resolved())

    result = run(world)

    assert result == StepResult(status="done", gate="liveness", output_ref=str(LOG_PATH))


# ── blocked ──────────────────────────────────────────────────────────────────


def test_a_blocked_file_is_the_question_the_operator_reads_verbatim() -> None:
    world = a_tail_world(story=a_story("blocked", "intent gap"))

    result = run(world)

    assert result.status == "blocked"
    assert result.park is not None
    assert result.park.kind == "blocked"
    assert result.park.reason == a_section("blocked", "intent gap")
    assert result.park.path == ROW_PATH


@pytest.mark.parametrize("condition", CONDITIONS)
def test_a_configuration_condition_stops_the_run_misconfigured(condition: str) -> None:
    world = a_tail_world(story=a_story("blocked", condition))

    result = run(world)

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == f"harness misconfigured: {condition}"


# ── the spec checkpoint ──────────────────────────────────────────────────────


def test_ready_for_dev_at_a_declared_spec_checkpoint_stops_for_the_operator() -> None:
    world = a_tail_world(
        story=a_story("ready-for-dev"), with_resolved=contracted(spec_checkpoint=True)
    )

    result = run(world)

    assert result.status == "checkpoint"
    assert result.park is not None
    assert (result.park.kind, result.park.reason) == ("checkpoint", "spec checkpoint")


# ── the retry path ───────────────────────────────────────────────────────────


def test_ready_for_dev_without_a_checkpoint_asks_for_the_rows_own_retry() -> None:
    world = a_tail_world(story=a_story("ready-for-dev"))

    result = run(world)

    assert result.status == "error"
    assert result.reason == "unexpected status: ready-for-dev"
    assert result.retry is not None
    assert (result.retry.prompt, result.retry.max, result.retry.resume_session) == (
        RETRY_PROMPT,
        RETRY_MAX,
        True,
    )
    assert result.park is None


def test_the_row_that_has_used_its_retries_parks_misconfigured_instead() -> None:
    world = a_tail_world(story=a_story("ready-for-dev"))

    result = AgentExecutor().execute(retried(world, RETRY_MAX))

    assert result.retry is None
    assert result.park is not None
    assert result.park.reason == "unexpected status: ready-for-dev"


def test_a_non_zero_exit_with_a_done_file_is_the_retry_path_too() -> None:
    world = a_tail_world(exit_code=1)

    result = run(world)

    assert result.status == "error"
    assert result.reason == "harness exit 1"
    assert result.retry is not None


def test_a_row_whose_retry_contract_names_no_prompt_never_retries() -> None:
    world = a_tail_world(
        story=a_story("draft"), with_resolved=contracted(retry={"max": 2, "prompt": None})
    )

    result = run(world)

    assert result.retry is None
    assert result.park is not None


def test_a_row_whose_retry_contract_names_no_max_never_retries() -> None:
    world = a_tail_world(
        story=a_story("draft"), with_resolved=contracted(retry={"max": None, "prompt": "go"})
    )

    result = run(world)

    assert result.retry is None


def test_a_row_with_no_retry_key_at_all_never_retries() -> None:
    row = contracted()
    del row["retry"]
    world = a_tail_world(story=a_story("draft"), with_resolved=row)

    result = run(world)

    assert result.retry is None
    assert result.park is not None


def test_a_retry_contract_that_is_not_a_mapping_is_no_contract() -> None:
    world = a_tail_world(story=a_story("draft"), with_resolved=contracted(retry="two"))

    result = run(world)

    assert result.retry is None


# ── liveness ─────────────────────────────────────────────────────────────────


def test_a_dispatch_that_wrote_no_file_parks_misconfigured() -> None:
    world = a_tail_world(story=None)

    result = run(world)

    assert result.status == "error"
    assert result.park is not None
    assert result.park.reason == "no story file"
    assert result.retry is None


def test_two_matching_files_are_both_named_in_the_stop() -> None:
    world = a_tail_world(files={OTHER_PATH: a_story()})

    result = run(world)

    assert result.park is not None
    assert result.park.reason == f"ambiguous story file: {STORY_PATH}, {OTHER_PATH}"


def test_a_file_the_harness_left_unparseable_names_the_file() -> None:
    world = a_tail_world(story="# Story 4-1\n\nno frontmatter\n")

    result = run(world)

    assert result.park is not None
    assert result.park.reason == f"no story file: frontmatter unreadable in {STORY_PATH}"


# ── what holds whatever the file said ────────────────────────────────────────


@pytest.mark.parametrize(
    "story",
    [
        a_story(),
        a_story("blocked", "intent gap"),
        a_story("blocked", "no subagents"),
        a_story("draft"),
        None,
    ],
    ids=["done", "blocked", "misconfigured", "retry", "no file"],
)
def test_the_rows_gate_survives_every_outcome(story: str | None) -> None:
    """NFR-2: a Story step is `liveness`, and the tail never re-decides that."""
    world = a_tail_world(story=story)

    assert run(world).gate == world.row.gate == "liveness"


@pytest.mark.parametrize(
    "story", [a_story(), a_story("blocked", "intent gap"), None], ids=["done", "blocked", "none"]
)
def test_the_attempt_is_fully_recorded_before_anything_is_routed(story: str | None) -> None:
    """AD-8: a parked attempt is as completely recorded as one that reached `done`."""
    world = a_tail_world(story=story)

    run(world)

    finished = world.attempts.attempts[world.attempt.id]
    assert finished.ended_at is not None
    assert finished.exit_code == 0
    assert finished.log_path == str(LOG_PATH)


@pytest.mark.parametrize(
    "story", [a_story(), a_story("blocked", "intent gap"), None], ids=["done", "blocked", "none"]
)
def test_every_result_carries_the_harness_log_the_operator_would_open(story: str | None) -> None:
    world = a_tail_world(story=story)

    assert run(world).output_ref == str(LOG_PATH)


def test_a_timeout_is_still_parked_before_the_file_is_ever_read() -> None:
    """A harness that never came back wrote nothing; `no story file` would be the wrong stop."""
    harness = FakeHarness()
    harness.results.append(
        HarnessResult(session_id="s-1", exit_code=None, timed_out=True, log_path=LOG_PATH)
    )
    world = a_tail_world(story=None, harness=harness, exit_code=0)

    result = run(world)

    assert result.park is not None
    assert result.park.kind == "timeout"


# ── the order AD-9 fixes ─────────────────────────────────────────────────────


def test_the_two_unimplemented_checks_are_named_where_ad_9_puts_them() -> None:
    """AD-9's tail order: the protected-path check (5.6) before the routing, the spend and
    budget read (5.7) after it. Both are seams in this story, and a seam nobody can find is
    a seam that gets filled in the wrong place."""
    body = inspect.getsource(agent_tail.tail)

    assert body.index("5.6") < body.index("route(") < body.index("5.7")


def test_neither_seam_is_answering_anything_yet() -> None:
    """A dispatch that modified a protected path or overspent still routes on its file
    here: both stops belong to the stories that land them, not to this one."""
    world = a_tail_world()

    result = run(world)

    assert result.park is None
    assert result.status == "done"


# ── the liveness glob, as one pure answer ────────────────────────────────────
# Operator decision, 2026-09-27: a row whose `spec_folder` resolves empty used to fall back
# to the absolute `/stories/-*.md`; the FR-16 fallback now needs a spec folder to stand on.


def test_declared_files_are_the_liveness_globs() -> None:
    row = resolved(expect={"files": ["artifacts/spec-*.md"], "status_in": []})

    assert agent_tail.liveness_globs(row) == ("artifacts/spec-*.md",)


def test_the_fr16_fallback_glob_is_built_from_the_spec_folder_and_story_id() -> None:
    row = resolved(expect={"status_in": ["done"]})

    assert agent_tail.liveness_globs(row) == (f"{SPEC_FOLDER}/stories/{STORY_ID}-*.md",)


def test_an_empty_spec_folder_globs_nothing_rather_than_the_filesystem_root() -> None:
    row = resolved(spec_folder="", expect={"status_in": ["done"]})

    assert agent_tail.liveness_globs(row) == ()


def test_a_row_with_no_expect_mapping_has_no_liveness_globs() -> None:
    assert agent_tail.liveness_globs(resolved()) == ()
