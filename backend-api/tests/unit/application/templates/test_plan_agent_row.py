"""What an `agent` row carries beside its `with`, and where each of those values came from.

The brief fixes the list: `story` (the entry, whole), `spec_folder`, `story_id`,
`prompt_extra`, `expect`, `retry`, `timeout_min` and the `pause_when` flag. Every one of
them is asserted here through `plan_run`, because a rule that only holds when the extras
function is called by hand is not a rule about plans.

Three shapes bind the entry, and all three are covered: a callee handed it as its declared
`item` input (`story@1`, the shipped case), a `for_each` in the same file binding it under
its own `as` name, and a step with no entry behind it at all.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.templates.agent_row import (
    EXPECT_KEY,
    PROMPT_EXTRA_KEY,
    RETRY_KEY,
    SPEC_CHECKPOINT_KEY,
    SPEC_FOLDER_KEY,
    STORY_ID_KEY,
    STORY_KEY,
)
from orchestrator.application.templates.model import ParsedTemplate
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import Plan, ResolvedTree
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

FOLDER = "docs/epic-1"
THINGS_PATH = f"{FOLDER}/things.yaml"
REF = fixtures.BASE_SHA

HEADER = """name: {name}
version: 1
inputs:
  project:     {{ type: project,    required: true }}
  repository:  {{ type: repository, required: true }}
  base_branch: {{ type: string,     required: true }}
  spec_folder: {{ type: path,       required: true }}
  harness:     {{ type: enum, values: [claude, codex, local], default: claude }}
steps:
"""

#: An `agent` step directly inside the loop that reads the list: the entry is the loop's.
IN_LOOP = (
    HEADER.format(name="in-loop")
    + """  - id: things
    for_each: "{{spec_folder}}/things.yaml"
    as: thing
    steps:
      - id: work
        uses: agent
        with: { harness: "{{harness}}" }
        pause_when: "thing.review"
        gate: liveness
"""
)

#: The same, except the Template binds `prompt_extra` itself and means what it bound.
IN_LOOP_WITH_PROMPT = IN_LOOP.replace(
    'with: { harness: "{{harness}}" }',
    'with: { harness: "{{harness}}", prompt_extra: "read the runbook" }',
)

#: An `agent` step no loop encloses: a dispatch with no entry behind it.
ALONE = (
    HEADER.format(name="alone")
    + """  - id: work
    uses: agent
    with: { harness: "{{harness}}" }
    gate: liveness
"""
)

THINGS = """
- id: t1
  review: true
  invoke_dev_with: read the brief first
- id: t2
"""


def _parsed(text: str) -> ParsedTemplate:
    result = validate(text, templates=FakeTemplateVersionRepository([]))

    assert result.template is not None, result.errors
    return result.template


def _git() -> FakeGit:
    return FakeGit(
        refs={fixtures.BASE_BRANCH: REF},
        files={(REF, THINGS_PATH): THINGS},
        listings={},
    )


def planned(text: str) -> Plan:
    return plan_run(
        ResolvedTree(root=_parsed(text)),
        fixtures.inputs(values={"spec_folder": FOLDER}),
        git=_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )


def resolved(plan: Plan, path: str) -> dict[str, Any]:
    return next(row for row in plan.rows if row.path == path).with_resolved


# --- the entry a callee was handed: the shipped `epic@1` -> `story@1` shape ------------------


def build_row() -> dict[str, Any]:
    plan = plan_run(
        fixtures.tree("epic"),
        fixtures.epic_inputs(),
        git=fixtures.epic_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )
    return resolved(plan, "stories[0].build")


def test_an_agent_row_carries_the_list_entry_whole() -> None:
    """`story: "{{story}}"` passes the mapping through, so the row holds the entry itself."""
    entry = build_row()[STORY_KEY]

    assert isinstance(entry, dict)
    assert entry["id"] == "1"
    assert entry["title"] == "The first story"


def test_an_agent_row_carries_the_spec_folder_it_will_be_dispatched_in() -> None:
    assert build_row()[SPEC_FOLDER_KEY] == fixtures.SPEC_FOLDER


def test_an_agent_row_carries_the_story_id_beside_the_rows_own() -> None:
    assert build_row()[STORY_ID_KEY] == "1"


def test_an_agent_row_carries_the_entrys_own_dispatch_instructions() -> None:
    assert build_row()[PROMPT_EXTRA_KEY] == fixtures.INVOKE_DEV_WITH


def test_an_agent_row_carries_its_expect_and_retry_with_the_globs_filled_in() -> None:
    row = build_row()

    assert row[EXPECT_KEY]["files"] == [f"{fixtures.SPEC_FOLDER}/stories/1-*.md"]
    assert row[EXPECT_KEY]["status_in"] == ["done", "blocked", "ready-for-dev"]
    assert row[RETRY_KEY]["max"] == fixtures.RETRY_MAX
    assert row[RETRY_KEY]["resume_session"] is True
    assert fixtures.SPEC_FOLDER in row[RETRY_KEY]["prompt"]


# --- the entry a loop in the same file bound ----------------------------------------------------


def test_a_loop_in_the_same_file_binds_the_entry_under_its_own_as_name() -> None:
    plan = planned(IN_LOOP)

    assert resolved(plan, "things[0].work")[STORY_KEY] == {
        "id": "t1",
        "review": True,
        "invoke_dev_with": "read the brief first",
    }


def test_the_entry_supplies_the_prompt_when_the_template_bound_none() -> None:
    assert resolved(planned(IN_LOOP), "things[0].work")[PROMPT_EXTRA_KEY] == (
        "read the brief first"
    )


def test_an_entry_that_says_nothing_extra_appends_nothing() -> None:
    assert resolved(planned(IN_LOOP), "things[1].work")[PROMPT_EXTRA_KEY] == ""


def test_what_the_template_bound_wins_over_the_entrys_own() -> None:
    """A Template that wrote a `prompt_extra` meant it; the entry is only the fallback."""
    assert resolved(planned(IN_LOOP_WITH_PROMPT), "things[0].work")[PROMPT_EXTRA_KEY] == (
        "read the runbook"
    )


def test_a_loop_over_anything_but_stories_belongs_to_no_story() -> None:
    """`story_id` is a Story's id, and `things.yaml` names no Story (FR-10)."""
    assert resolved(planned(IN_LOOP), "things[0].work")[STORY_ID_KEY] is None


def test_the_pause_flag_reads_the_entrys_field_and_adds_no_row() -> None:
    plan = planned(IN_LOOP)

    assert resolved(plan, "things[0].work")[SPEC_CHECKPOINT_KEY] is True
    assert resolved(plan, "things[1].work")[SPEC_CHECKPOINT_KEY] is False
    assert [row.path for row in plan.rows] == ["plan", "things[0].work", "things[1].work"]


# --- no entry at all ------------------------------------------------------------------------------


def test_an_agent_step_outside_every_loop_carries_no_entry() -> None:
    row = resolved(planned(ALONE), "work")

    assert (row[STORY_KEY], row[STORY_ID_KEY], row[PROMPT_EXTRA_KEY]) == (None, None, "")


def test_an_agent_step_outside_every_loop_still_carries_its_folder_and_contract() -> None:
    row = resolved(planned(ALONE), "work")

    assert row[SPEC_FOLDER_KEY] == FOLDER
    assert row[SPEC_CHECKPOINT_KEY] is False
    assert row[RETRY_KEY] == {"max": None, "prompt": None, "resume_session": True}


# --- the dispatch target the whole Run is planned around -------------------------------------


def test_an_agent_row_carries_the_harness_the_run_chose() -> None:
    """`story@1` binds `{{harness}}`; the Run is what that name resolves to."""
    assert build_row()["harness"] == fixtures.DEFAULT_HARNESS


def test_an_agent_row_carries_the_model_the_run_chose() -> None:
    plan = plan_run(
        fixtures.tree("epic"),
        fixtures.epic_inputs(harness="codex", model="a-model"),
        git=fixtures.epic_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )
    row = resolved(plan, "stories[0].build")

    assert (row["harness"], row["model"]) == ("codex", "a-model")


def test_a_run_that_chose_no_model_says_so_with_nothing_rather_than_with_none() -> None:
    """`{{model}}` unbound is `""`; the four characters `None` would reach a harness."""
    assert build_row()["model"] == ""
