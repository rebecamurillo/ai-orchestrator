"""`application/rules/routing.py`: the FR-16 table, one test per row.

`route` is the whole decision the `agent` kind makes about what a dispatch reached, and it
is pure — a parsed Story file, the names the liveness glob matched, the harness's exit code
and the row's own `spec_checkpoint` / `retry` contract in, one `StepResult` out. No port, no
clock, no I/O, so every row of the table is a call here rather than a wired world.

Two invariants hold across every row and are asserted on every one of them: the gate is the
row's own (`liveness` — a Story step is never green, NFR-2), and every stop is one `Park`
kind of PRD §4.6.
"""

from __future__ import annotations

import pytest

from orchestrator.application.rules.routing import (
    AMBIGUOUS_STORY_FILE,
    CONFIGURATION_CONDITIONS,
    HARNESS_EXIT,
    MISCONFIGURED_HARNESS,
    NO_STORY_FILE,
    SPEC_CHECKPOINT,
    UNEXPECTED_STATUS,
    UNREADABLE_FRONTMATTER,
    route,
)
from orchestrator.application.story_file import StoryFile
from orchestrator.domain.statuses import PARK_KINDS
from orchestrator.domain.values import Retry, StepResult

GATE = "liveness"
ROW_PATH = "epics[0].stories[3].build"
ONE = ("specs/notifications/stories/4-1-notify.md",)
SECTION = "## Auto Run Result\n\nStatus: blocked\nBlocking condition: intent gap"
RETRY = Retry(prompt="Finish the story and write that file.", max=2, resume_session=True)


def a_story(status: str, condition: str | None = None, result: str = "") -> StoryFile:
    return StoryFile(
        path=ONE[0], status=status, auto_run_result=result, blocking_condition=condition
    )


def routed(  # noqa: PLR0913 — one keyword per column of the FR-16 table
    story: StoryFile | None = None,
    *,
    files: tuple[str, ...] = ONE,
    exit_code: int | None = 0,
    spec_checkpoint: bool = False,
    retry_count: int = 0,
    retry: Retry | None = RETRY,
) -> StepResult:
    return route(
        story,
        files,
        exit_code,
        spec_checkpoint,
        retry_count,
        retry,
        gate=GATE,
        path=ROW_PATH,
    )


# ── done ─────────────────────────────────────────────────────────────────────


def test_one_file_at_done_and_a_clean_exit_is_the_only_way_forward() -> None:
    result = routed(a_story("done"))

    assert result == StepResult(status="done", gate=GATE)


# ── blocked ──────────────────────────────────────────────────────────────────


def test_a_blocked_file_parks_blocked_with_its_whole_section_as_the_reason() -> None:
    result = routed(a_story("blocked", "intent gap", SECTION))

    assert result.status == "blocked"
    assert result.park is not None
    assert result.park.kind == "blocked"
    assert result.park.reason == SECTION
    assert result.park.path == ROW_PATH
    assert result.reason == SECTION


def test_a_blocked_file_with_no_condition_at_all_is_still_a_question() -> None:
    result = routed(a_story("blocked", None, SECTION))

    assert result.status == "blocked"
    assert result.park is not None
    assert result.park.kind == "blocked"


@pytest.mark.parametrize("condition", CONFIGURATION_CONDITIONS)
def test_each_configuration_condition_is_a_misconfigured_stop_and_not_a_question(
    condition: str,
) -> None:
    """No Answer is offered on these: the UI reads `park_kind`, and this one is not `blocked`."""
    result = routed(a_story("blocked", condition, SECTION))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == f"harness misconfigured: {condition}"
    assert result.reason == MISCONFIGURED_HARNESS.format(condition=condition)


def test_the_seven_conditions_are_the_whole_configuration_list() -> None:
    assert CONFIGURATION_CONDITIONS == (
        "no subagents",
        "no stories.yaml found",
        "story id not found in stories.yaml",
        "version-control metadata not writable",
        "no epic spec found",
        "unrecognized status in existing story file",
        "ambiguous story file match",
    )


# ── the spec checkpoint ──────────────────────────────────────────────────────


def test_ready_for_dev_at_a_spec_checkpoint_stops_for_the_operator() -> None:
    result = routed(a_story("ready-for-dev"), spec_checkpoint=True)

    assert result.status == "checkpoint"
    assert result.park is not None
    assert result.park.kind == "checkpoint"
    assert result.park.reason == SPEC_CHECKPOINT
    assert SPEC_CHECKPOINT == "spec checkpoint"


def test_a_spec_checkpoint_on_any_other_status_decides_nothing() -> None:
    """The halt is what produces `ready-for-dev`; a `done` file passed it long ago."""
    result = routed(a_story("done"), spec_checkpoint=True)

    assert result.status == "done"


# ── the retry path ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["ready-for-dev", "draft", "in-progress", "in-review", "wat"])
def test_a_status_that_routes_nowhere_retries_while_the_contract_allows(status: str) -> None:
    result = routed(a_story(status))

    assert result.status == "error"
    assert result.reason == f"unexpected status: {status}"
    assert result.retry == RETRY
    assert result.park is None


@pytest.mark.parametrize("status", ["ready-for-dev", "draft", "in-progress", "in-review", "wat"])
def test_the_same_status_parks_misconfigured_once_the_retries_are_used_up(status: str) -> None:
    result = routed(a_story(status), retry_count=2)

    assert result.status == "error"
    assert result.retry is None
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == UNEXPECTED_STATUS.format(status=status)


def test_a_row_that_declared_no_retry_contract_parks_on_the_first_unexpected_status() -> None:
    result = routed(a_story("draft"), retry=None)

    assert result.retry is None
    assert result.park is not None
    assert result.park.kind == "misconfigured"


def test_a_retry_max_of_zero_is_a_contract_that_never_fires() -> None:
    result = routed(a_story("draft"), retry=RETRY.model_copy(update={"max": 0}))

    assert result.retry is None
    assert result.park is not None


# ── the exit code ────────────────────────────────────────────────────────────


def test_a_done_file_after_a_non_zero_exit_takes_the_retry_path() -> None:
    result = routed(a_story("done"), exit_code=1)

    assert result.status == "error"
    assert result.reason == HARNESS_EXIT.format(code=1)
    assert result.retry == RETRY
    assert result.park is None


def test_the_exhausted_exit_code_parks_misconfigured_with_the_same_sentence() -> None:
    result = routed(a_story("done"), exit_code=1, retry_count=2)

    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == "harness exit 1"


def test_a_non_zero_exit_never_overrides_the_status_the_file_reports() -> None:
    """The file is what FR-16 routes on; the code only decides for a `done` one."""
    result = routed(a_story("blocked", "intent gap", SECTION), exit_code=1)

    assert result.status == "blocked"
    assert result.park is not None
    assert result.park.kind == "blocked"


def test_a_harness_that_reported_no_exit_code_is_not_a_failed_one() -> None:
    """`exit_code` is `None` only for a process that never returned one — a timeout, which
    the executor parked before the routing rule was ever reached."""
    assert routed(a_story("done"), exit_code=None).status == "done"


# ── liveness ─────────────────────────────────────────────────────────────────


def test_no_matching_file_is_a_misconfigured_stop_and_never_a_retry() -> None:
    result = routed(None, files=())

    assert result.status == "error"
    assert result.retry is None
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == NO_STORY_FILE
    assert NO_STORY_FILE == "no story file"


def test_two_matching_files_name_both_of_them_in_alphabetical_order() -> None:
    result = routed(None, files=("b.md", "a.md"))

    assert result.park is not None
    assert result.park.reason == "ambiguous story file: a.md, b.md"
    assert result.park.reason == AMBIGUOUS_STORY_FILE.format(names="a.md, b.md")


def test_ambiguity_beats_a_file_that_did_parse() -> None:
    """Two matches is a stop whichever of them happened to be readable."""
    result = routed(a_story("done"), files=("a.md", "b.md"))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"


def test_one_file_whose_frontmatter_did_not_parse_names_the_file() -> None:
    result = routed(None, files=("a.md",))

    assert result.park is not None
    assert result.park.reason == "no story file: frontmatter unreadable in a.md"
    assert result.park.reason == UNREADABLE_FRONTMATTER.format(name="a.md")


@pytest.mark.parametrize("files", [(), ("a.md",), ("a.md", "b.md")])
def test_no_liveness_failure_is_ever_retried(files: tuple[str, ...]) -> None:
    """AD-9: `misconfigured` is never re-executed automatically, however much retry is left."""
    result = routed(None, files=files, retry_count=0)

    assert result.retry is None


# ── what holds on every row ──────────────────────────────────────────────────


CASES: tuple[StepResult, ...] = (
    routed(a_story("done")),
    routed(a_story("done"), exit_code=1),
    routed(a_story("done"), exit_code=1, retry_count=2),
    routed(a_story("blocked", "intent gap", SECTION)),
    routed(a_story("blocked", "no subagents", SECTION)),
    routed(a_story("ready-for-dev"), spec_checkpoint=True),
    routed(a_story("ready-for-dev")),
    routed(a_story("draft"), retry_count=2),
    routed(None, files=()),
    routed(None, files=("a.md", "b.md")),
    routed(None, files=("a.md",)),
)


@pytest.mark.parametrize("result", CASES, ids=lambda result: str(result.reason))
def test_every_row_of_the_table_keeps_the_rows_own_gate(result: StepResult) -> None:
    assert result.gate == GATE


@pytest.mark.parametrize("result", CASES, ids=lambda result: str(result.reason))
def test_every_stop_is_one_park_kind_of_the_table_on_this_row(result: StepResult) -> None:
    if result.park is None:
        return
    assert result.park.kind in PARK_KINDS
    assert result.park.path == ROW_PATH


@pytest.mark.parametrize("result", CASES, ids=lambda result: str(result.reason))
def test_no_row_of_the_table_ever_asks_for_a_redispatch(result: StepResult) -> None:
    """Going back to an earlier row is the verify step's decision, never this one's."""
    assert result.redispatch is None
