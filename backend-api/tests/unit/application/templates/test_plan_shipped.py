"""The four shipped Templates, planned: the story's acceptance criteria, row by row.

This is the module that says what a Run *is*. `repo-init@1`, `epic@1` and `initiative@1`
are expanded against a scripted `Git`, and what is asserted is the whole row list — paths,
labels, gates, statuses and the commit each list file was read at — because AD-7's promise
is that *What will run* is exactly what runs, and a promise about a list is only kept by
asserting the list.

Nothing here is a second reading of the Template files: `plan_fixtures` runs the same text
`make lint` ships through the same `validate()` the API calls (AD-15).
"""

from __future__ import annotations

import pytest

from orchestrator.application.dto import RunInputs
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import (
    AMBIGUOUS_STORY_FILE,
    ENTRY_MISSING_FIELDS,
    ID_NOT_PREFIX_FREE,
    ON_FAIL_KEY,
    REASON_ALREADY_DONE,
    REASON_NO_QUALITY_GATE,
    Plan,
    PlanError,
)
from orchestrator.domain.values import PlannedRow, Redispatch
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit

#: What `repo-init@1` declares for its `bmad.install` step, and how many files an
#: Initiative of two epics reads.
INSTALL_TIMEOUT_MIN = 30
INITIATIVE_LIST_FILES = 3

#: How many Stories `plan_fixtures.EPIC_STORIES` holds.
STORY_COUNT = 3

#: What a declared branch becomes: no Run works on the name a Template wrote, it works on
#: the first ordinal of it the origin does not already hold (`templates/branches.py`).
#: Nothing in these fixtures holds one, so every Run here is the first.
FIRST_ORDINAL = "-1"
INIT_BRANCH = f"{fixtures.INIT_BRANCH}{FIRST_ORDINAL}"
INITIATIVE_BRANCH = f"{fixtures.INITIATIVE_BRANCH}{FIRST_ORDINAL}"


def plan(name: str, run_inputs: RunInputs, git: FakeGit) -> Plan:
    return plan_run(
        fixtures.tree(name),
        run_inputs,
        git=git,
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )


def paths(result: Plan) -> list[str]:
    return [row.path for row in result.rows]


def row(result: Plan, path: str) -> PlannedRow:
    return next(entry for entry in result.rows if entry.path == path)


# --- AC1: repo-init@1, whose working branch the remote does not hold yet ---------------------


@pytest.fixture
def repo_init() -> Plan:
    return plan("repo-init", fixtures.inputs(), fixtures.repo_init_git())


def test_repo_init_plans_from_the_base_when_its_branch_is_not_on_the_remote(
    repo_init: Plan,
) -> None:
    assert repo_init.plan_ref == fixtures.BASE_SHA


def test_repo_init_is_six_rows_in_file_order(repo_init: Plan) -> None:
    assert paths(repo_init) == ["plan", "checkout", "install", "commit", "push", "link"]
    assert [row.seq for row in repo_init.rows] == [1, 2, 3, 4, 5, 6]


def test_repo_init_gates_are_five_deterministic_and_then_the_live_one(repo_init: Plan) -> None:
    assert [row.gate for row in repo_init.rows] == ["deterministic"] * 5 + ["liveness"]


def test_repo_init_checkout_substitutes_the_base_branch_and_the_literal_branch(
    repo_init: Plan,
) -> None:
    resolved = row(repo_init, "checkout").with_resolved

    assert {key: value for key, value in resolved.items() if key != "timeout_min"} == {
        "base": fixtures.BASE_BRANCH,
        "branch": INIT_BRANCH,
    }


def test_repo_init_carries_the_resolved_timeout_of_every_row(repo_init: Plan) -> None:
    """`PlannedRow` has no timeout field, so a complete plan carries it here (AD-7)."""
    assert row(repo_init, "install").with_resolved["timeout_min"] == INSTALL_TIMEOUT_MIN


def test_repo_init_pushes_the_branch_it_created(repo_init: Plan) -> None:
    assert row(repo_init, "push").with_resolved["branch"] == INIT_BRANCH


def test_repo_init_reads_no_list_file_at_all(repo_init: Plan) -> None:
    assert repo_init.plan_refs == {}


# --- AC2: epic@1 over three stories -----------------------------------------------------------


EPIC_ROWS = [
    "plan",
    "checkout",
    "baseline",
    "stories[0].sync",
    "stories[0].build",
    "stories[0].verify",
    "stories[0].commit-guard",
    "stories[1].sync",
    "stories[1].build",
    "stories[1].verify",
    "stories[1].commit-guard",
    "stories[1].after",
    "stories[2].sync",
    "stories[2].build",
    "stories[2].verify",
    "stories[2].commit-guard",
    "push",
    "link",
]

THIRD_STORY = [path for path in EPIC_ROWS if path.startswith("stories[2]")]


@pytest.fixture
def epic() -> Plan:
    return plan("epic", fixtures.epic_inputs(), fixtures.epic_git())


def test_epic_plans_from_its_own_branch_when_the_remote_holds_it(epic: Plan) -> None:
    assert epic.plan_ref == fixtures.WORK_SHA


def test_epic_expands_one_frame_per_story_with_the_checkpoint_story_two_declared(
    epic: Plan,
) -> None:
    assert paths(epic) == EPIC_ROWS


def test_epic_labels_read_the_story_then_the_step(epic: Plan) -> None:
    assert row(epic, "stories[0].build").label == "story 1 · build"


def test_an_item_checkpoint_reads_as_the_stop_it_is(epic: Plan) -> None:
    assert row(epic, "stories[1].after").label == "story 2 · done checkpoint"


def test_every_story_row_carries_its_frame_and_the_story_it_belongs_to(epic: Plan) -> None:
    for path in EPIC_ROWS:
        entry = row(epic, path)
        if not path.startswith("stories["):
            continue
        assert entry.frame == path[: path.index("]") + 1], path
        assert entry.story_id is not None, path


def test_the_story_id_is_the_list_files_own_id(epic: Plan) -> None:
    assert row(epic, "stories[2].commit-guard").story_id == "3"


def test_a_story_whose_file_is_already_done_is_skipped_row_by_row(epic: Plan) -> None:
    for path in THIRD_STORY:
        entry = row(epic, path)
        assert (entry.status, entry.reason) == ("skipped", REASON_ALREADY_DONE), path


def test_a_story_whose_file_is_not_done_is_planned(epic: Plan) -> None:
    assert row(epic, "stories[0].build").status == "planned"


def test_the_commit_message_of_a_story_row_carries_the_entrys_own_words(epic: Plan) -> None:
    resolved = row(epic, "stories[0].commit-guard").with_resolved

    assert resolved["message"] == "story 1: The first story (orchestrator)"


def test_the_stories_list_is_recorded_at_the_commit_it_was_read_at(epic: Plan) -> None:
    assert epic.plan_refs == {f"{fixtures.SPEC_FOLDER}/stories.yaml": fixtures.WORK_SHA}


def test_the_stories_list_is_read_once() -> None:
    git = fixtures.epic_git()

    plan("epic", fixtures.epic_inputs(), git)

    reads = [call for call in git.called("read_file") if call[2].endswith("stories.yaml")]
    assert len(reads) == 1


def test_each_story_folder_is_listed_once_per_ref() -> None:
    git = fixtures.epic_git()

    plan("epic", fixtures.epic_inputs(), git)

    assert git.called("list_files") == [(fixtures.BASE, fixtures.WORK_SHA, fixtures.STORIES_DIR)]


# --- AC3: the same Run asked to review what is already done -------------------------------------


def test_a_re_review_plans_the_story_whose_file_is_already_done() -> None:
    result = plan("epic", fixtures.epic_inputs(re_review_done=True), fixtures.epic_git())

    for path in THIRD_STORY:
        entry = row(result, path)
        assert (entry.status, entry.reason) == ("planned", None), path


DONE_AND_PAUSED = """
- id: "3"
  title: The third story
  description: does the third thing
  done_checkpoint: true
"""


def test_a_checkpoint_of_a_story_that_is_already_done_is_skipped_with_the_rest() -> None:
    """Every row of the frame, checkpoint rows included: nobody stops at a Story nobody runs."""
    git = FakeGit(
        refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA, fixtures.EPIC_BRANCH: fixtures.WORK_SHA},
        files={
            (fixtures.WORK_SHA, f"{fixtures.SPEC_FOLDER}/stories.yaml"): DONE_AND_PAUSED,
            (fixtures.WORK_SHA, fixtures.DONE_STORY_PATH): fixtures.story_file("done"),
        },
        listings={(fixtures.WORK_SHA, fixtures.STORIES_DIR): [fixtures.DONE_STORY_PATH]},
    )

    result = plan("epic", fixtures.epic_inputs(), git)
    entry = row(result, "stories[0].after")

    assert (entry.status, entry.reason) == ("skipped", REASON_ALREADY_DONE)


def test_two_files_for_one_story_stop_the_plan_even_on_a_re_review() -> None:
    """Which file is the Story's is a fact about the repository, not about the request:
    a plan that refused it must not plan it because the re-review box was ticked."""
    git = fixtures.epic_git()
    git.listings[(fixtures.WORK_SHA, fixtures.STORIES_DIR)] = [
        fixtures.DONE_STORY_PATH,
        f"{fixtures.STORIES_DIR}/3-a-second-file.md",
    ]

    with pytest.raises(PlanError) as raised:
        plan("epic", fixtures.epic_inputs(re_review_done=True), git)

    assert (raised.value.reason, raised.value.item) == (AMBIGUOUS_STORY_FILE, "3")


# --- AC4: a repository with no quality gate -------------------------------------------------------


def test_every_shell_row_is_skipped_when_the_repository_states_no_quality_gate() -> None:
    result = plan(
        "epic",
        fixtures.epic_inputs(repository=fixtures.NO_QUALITY_GATE),
        fixtures.epic_git(),
    )

    shell_rows = [entry for entry in result.rows if entry.kind == "shell"]
    assert [entry.path for entry in shell_rows] == [
        "baseline",
        "stories[0].verify",
        "stories[1].verify",
        "stories[2].verify",
    ]
    for entry in shell_rows[:3]:
        assert (entry.status, entry.reason) == ("skipped", REASON_NO_QUALITY_GATE), entry.path


def test_the_already_done_reason_wins_over_the_missing_quality_gate() -> None:
    """A row of a story nobody is going to run says why the story is not running."""
    result = plan(
        "epic",
        fixtures.epic_inputs(repository=fixtures.NO_QUALITY_GATE),
        fixtures.epic_git(),
    )

    assert row(result, "stories[2].verify").reason == REASON_ALREADY_DONE


# --- AC5: initiative@1 over two epics and eight stories ----------------------------------------


@pytest.fixture
def initiative() -> Plan:
    return plan("initiative", fixtures.initiative_inputs(), fixtures.initiative_git())


def epic_frame(index: int, *, after: bool) -> list[str]:
    prefix = f"epics[{index}]"
    rows = [f"{prefix}.checkout", f"{prefix}.baseline"]
    for story in range(4):
        rows += [
            f"{prefix}.stories[{story}].{step}"
            for step in ("sync", "build", "verify", "commit-guard")
        ]
    rows += [f"{prefix}.push", f"{prefix}.link"]
    if after:
        rows.append(f"{prefix}.after")
    return rows


def test_an_initiative_plans_from_the_base_because_it_checks_nothing_out_itself(
    initiative: Plan,
) -> None:
    assert initiative.plan_ref == fixtures.BASE_SHA


def test_an_initiative_expands_one_frame_per_epic_and_one_per_story(initiative: Plan) -> None:
    assert paths(initiative) == [
        "plan",
        *epic_frame(0, after=True),
        *epic_frame(1, after=False),
    ]


def test_a_nested_frame_reads_the_epic_then_the_story_then_the_step(initiative: Plan) -> None:
    assert row(initiative, "epics[0].stories[0].build").label == "epic 1 · story 4-1 · build"


def test_an_epic_row_outside_every_story_reads_the_epic_then_the_step(initiative: Plan) -> None:
    """The brief's second label example: an epic frame counts from one, by place."""
    assert row(initiative, "epics[1].checkout").label == "epic 2 · checkout"


def test_a_row_inside_a_nested_frame_names_the_innermost_frame(initiative: Plan) -> None:
    entry = row(initiative, "epics[0].stories[3].build")

    assert (entry.frame, entry.story_id) == ("epics[0].stories[3]", "4-4")


def test_an_epic_row_belongs_to_the_epic_frame_and_to_no_story(initiative: Plan) -> None:
    entry = row(initiative, "epics[1].push")

    assert (entry.frame, entry.story_id) == ("epics[1]", None)


def test_an_epic_works_on_the_branch_its_list_entry_named(initiative: Plan) -> None:
    assert row(initiative, "epics[0].checkout").with_resolved["branch"] == INITIATIVE_BRANCH


def test_each_epics_spec_folder_is_the_initiative_folder_plus_its_own(
    initiative: Plan,
) -> None:
    resolved = row(initiative, "epics[1].stories[0].build").with_resolved

    assert resolved["args"]["spec_folder"] == f"{fixtures.INITIATIVE_FOLDER}/epic-2"


def test_every_list_file_the_initiative_read_is_recorded_at_the_base(initiative: Plan) -> None:
    assert initiative.plan_refs == {
        f"{fixtures.INITIATIVE_FOLDER}/epics.yaml": fixtures.BASE_SHA,
        f"{fixtures.INITIATIVE_FOLDER}/epic-1/stories.yaml": fixtures.BASE_SHA,
        f"{fixtures.INITIATIVE_FOLDER}/epic-2/stories.yaml": fixtures.BASE_SHA,
    }


def test_each_list_file_is_read_exactly_once() -> None:
    git = fixtures.initiative_git()

    plan("initiative", fixtures.initiative_inputs(), git)

    reads = git.called("read_file")
    assert len(reads) == len(set(reads))
    assert len(reads) == INITIATIVE_LIST_FILES


def test_a_list_file_absent_at_the_base_is_read_at_the_epics_own_branch() -> None:
    """The Initiative assumption: the epics list is on the base, an epic's list may not be."""
    git = fixtures.initiative_git(stories_at=fixtures.WORK_SHA)

    result = plan("initiative", fixtures.initiative_inputs(), git)

    assert result.plan_refs[f"{fixtures.INITIATIVE_FOLDER}/epic-1/stories.yaml"] == (
        fixtures.WORK_SHA
    )
    assert result.plan_ref == fixtures.BASE_SHA


# --- AC6: a list file the Operator has to fix --------------------------------------------------


def epic_git_with(stories: str) -> FakeGit:
    return FakeGit(
        refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA, fixtures.EPIC_BRANCH: fixtures.WORK_SHA},
        files={(fixtures.WORK_SHA, f"{fixtures.SPEC_FOLDER}/stories.yaml"): stories},
        listings={},
    )


NOT_PREFIX_FREE = """
- id: "4-1"
  title: One
  description: d
- id: "4-1-a"
  title: One a
  description: d
"""

INCOMPLETE = """
- id: "4-1"
  title: One
"""

PREFIX_FREE = """
- id: "4-1"
  title: One
  description: d
- id: "4-10"
  title: Ten
  description: d
"""


def test_ids_that_are_not_prefix_free_stop_the_plan_naming_the_entry() -> None:
    with pytest.raises(PlanError) as raised:
        plan("epic", fixtures.epic_inputs(), epic_git_with(NOT_PREFIX_FREE))

    assert raised.value.reason == ID_NOT_PREFIX_FREE
    assert (raised.value.template, raised.value.version, raised.value.item) == (
        "epic",
        1,
        "4-1-a",
    )
    assert raised.value.line is not None


def test_an_entry_missing_a_required_field_stops_the_plan_naming_the_entry() -> None:
    with pytest.raises(PlanError) as raised:
        plan("epic", fixtures.epic_inputs(), epic_git_with(INCOMPLETE))

    assert raised.value.reason == ENTRY_MISSING_FIELDS
    assert raised.value.item == "4-1"


def test_ids_that_only_share_a_prefix_plan_normally() -> None:
    result = plan("epic", fixtures.epic_inputs(), epic_git_with(PREFIX_FREE))

    assert row(result, "stories[1].build").story_id == "4-10"


# --- the base branch itself --------------------------------------------------------------------


def test_a_base_branch_the_remote_does_not_hold_stops_the_plan() -> None:
    with pytest.raises(PlanError) as raised:
        plan("repo-init", fixtures.inputs(), FakeGit(refs={}, files={}, listings={}))

    assert raised.value.item == fixtures.BASE_BRANCH


# --- the pins the Run records ------------------------------------------------------------------


def test_the_pinned_versions_of_an_initiative_are_its_whole_call_tree() -> None:
    pinned = fixtures.tree("initiative").pinned_versions()

    assert [ref.name for ref in pinned] == ["initiative", "epic", "story"]


# --- how a failed row is routed: what 4.7's executors read off the row -------------------------


def test_a_row_that_declares_no_on_fail_carries_none(epic: Plan) -> None:
    """Absent is the DSL's own default, `escalate`; a row does not restate it."""
    assert ON_FAIL_KEY not in row(epic, "checkout").with_resolved


def test_a_plain_on_fail_is_the_word_the_template_wrote(epic: Plan) -> None:
    """`templates/epic.yaml` declares `on_fail: fail` on `baseline`."""
    assert row(epic, "baseline").with_resolved[ON_FAIL_KEY] == "fail"


def test_a_redispatch_is_resolved_to_the_seq_of_the_row_it_goes_back_to(epic: Plan) -> None:
    """`templates/story.yaml` declares `on_fail: {redispatch: build, max: 1}` on `verify`."""
    routed = row(epic, "stories[0].verify").with_resolved[ON_FAIL_KEY]

    assert routed == {"target_seq": row(epic, "stories[0].build").seq, "max": 1}


def test_the_executor_can_build_its_redispatch_from_the_row_and_nothing_else(epic: Plan) -> None:
    """The binding constraint: `Redispatch(**with_resolved["on_fail"])` and no other input."""
    routed = row(epic, "stories[1].verify").with_resolved[ON_FAIL_KEY]

    assert Redispatch(**routed) == Redispatch(target_seq=row(epic, "stories[1].build").seq, max=1)


def test_each_story_redispatches_inside_its_own_frame_and_never_into_another(epic: Plan) -> None:
    """Three Stories, three different targets — the first Story's build is not the third's."""
    targets = [
        row(epic, f"stories[{index}].verify").with_resolved[ON_FAIL_KEY]["target_seq"]
        for index in range(STORY_COUNT)
    ]

    assert targets == [row(epic, f"stories[{index}].build").seq for index in range(STORY_COUNT)]


def test_a_redispatch_inside_a_nested_frame_resolves_within_that_frame(initiative: Plan) -> None:
    """`epics[1].stories[0].verify` goes back to its own epic's Story, not to `epics[0]`'s."""
    routed = row(initiative, "epics[1].stories[0].verify").with_resolved[ON_FAIL_KEY]

    assert routed["target_seq"] == row(initiative, "epics[1].stories[0].build").seq
    assert routed["target_seq"] > row(initiative, "epics[0].stories[3].build").seq


def test_a_redispatch_always_points_backwards(initiative: Plan) -> None:
    for entry in initiative.rows:
        routed = entry.with_resolved.get(ON_FAIL_KEY)
        if isinstance(routed, dict):
            assert routed["target_seq"] < entry.seq, entry.path


def test_an_agent_rows_escalate_when_is_carried_verbatim(epic: Plan) -> None:
    """No consumer in this epic; Epic 5 needs a source and the plan is the only one (AD-7)."""
    assert row(epic, "stories[0].build").with_resolved["escalate_when"] == (
        "output.status == blocked"
    )
