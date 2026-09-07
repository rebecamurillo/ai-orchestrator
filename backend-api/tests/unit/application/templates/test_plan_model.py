"""The planner's vocabulary: its error, its reasons, its constants and its two values.

`PlanError` is an `Invalid`, which is what makes a plan-time refusal a 422 with no new
mapping in `api/errors.py` (`DOMAIN_STATUS`), and it carries the five fields a
`ProblemError` renders. The gate table below is the other rule worth a test of its own: a
row the planner inserts carries its kind's own `gate_default`, read from `KIND_META` rather
than written out again, exactly as `application/graph.py::_item_checkpoint` reads it.
"""

from __future__ import annotations

import pytest

from orchestrator.application.steps import CHECKPOINT_KIND, KIND_META, PLAN_KIND
from orchestrator.application.templates.plan_model import (
    AFTER_ITEM,
    AFTER_LABEL,
    AMBIGUOUS_STORY_FILE,
    BASE_BRANCH_NOT_FOUND,
    BEFORE_ITEM,
    CALLEE_NOT_RESOLVED,
    DUPLICATE_ENTRY_ID,
    ENTRY_MISSING_FIELDS,
    ID_NOT_PREFIX_FREE,
    INSERTED_GATE,
    LABEL_SEPARATOR,
    LIST_FILE_NOT_A_LIST,
    LIST_FILE_NOT_FOUND,
    PATH_SEPARATOR,
    PLAN_PATH,
    REASON_ALREADY_DONE,
    REASON_NO_COMMAND,
    REASON_NO_QUALITY_GATE,
    REDISPATCH_MAX,
    REDISPATCH_TARGET_SEQ,
    Plan,
    PlanError,
    Redispatched,
)
from orchestrator.domain.errors import Invalid
from orchestrator.domain.values import Redispatch
from tests.unit.application.templates import plan_fixtures as fixtures


def test_a_plan_error_is_an_invalid_so_the_api_answers_422_with_no_new_mapping() -> None:
    error = PlanError(reason=LIST_FILE_NOT_FOUND)

    assert isinstance(error, Invalid)


def test_a_plan_error_carries_the_five_fields_a_problem_error_renders() -> None:
    error = PlanError(reason=ENTRY_MISSING_FIELDS, template="epic", version=1, line=27, item="4-1")

    assert (error.reason, error.template, error.version) == (ENTRY_MISSING_FIELDS, "epic", 1)
    assert (error.line, error.item) == (27, "4-1")


def test_a_plan_error_names_the_reason_and_the_item_when_it_is_printed() -> None:
    error = PlanError(reason=AMBIGUOUS_STORY_FILE, item="4-1")

    assert AMBIGUOUS_STORY_FILE in str(error)
    assert "4-1" in str(error)


def test_a_plan_error_with_no_position_still_says_what_went_wrong() -> None:
    assert BASE_BRANCH_NOT_FOUND in str(PlanError(reason=BASE_BRANCH_NOT_FOUND))


@pytest.mark.parametrize(
    "reason",
    [
        LIST_FILE_NOT_FOUND,
        LIST_FILE_NOT_A_LIST,
        ENTRY_MISSING_FIELDS,
        DUPLICATE_ENTRY_ID,
        ID_NOT_PREFIX_FREE,
        AMBIGUOUS_STORY_FILE,
        CALLEE_NOT_RESOLVED,
        BASE_BRANCH_NOT_FOUND,
    ],
)
def test_every_plan_reason_is_a_sentence_an_operator_reads(reason: str) -> None:
    assert reason == reason.lower()
    assert reason.strip() == reason


@pytest.mark.parametrize("reason", [REASON_ALREADY_DONE, REASON_NO_QUALITY_GATE, REASON_NO_COMMAND])
def test_every_skipped_reason_is_a_sentence_an_operator_reads(reason: str) -> None:
    assert reason == reason.lower()


def test_the_path_and_label_constants_are_the_two_separators_and_nothing_else() -> None:
    assert (PLAN_PATH, PATH_SEPARATOR, LABEL_SEPARATOR) == ("plan", ".", " · ")
    assert (BEFORE_ITEM, AFTER_ITEM, AFTER_LABEL) == ("before", "after", "done checkpoint")


# --- the gate a planner-inserted row carries -------------------------------------------------


@pytest.mark.parametrize("kind", [PLAN_KIND, CHECKPOINT_KIND])
def test_an_inserted_row_carries_its_kinds_own_default_gate(kind: str) -> None:
    """Nobody left these ungated, so they are not `unvalidated` (NFR-2)."""
    assert INSERTED_GATE[kind] == KIND_META[kind].gate_default


def test_a_kind_with_no_gate_of_its_own_is_not_in_the_table() -> None:
    """A call is a path segment, not a row; there is no gate for it to carry (AD-15)."""
    assert "template" not in INSERTED_GATE


# --- the resolved tree -----------------------------------------------------------------------


def test_a_resolved_tree_answers_a_callee_it_holds() -> None:
    tree = fixtures.tree("epic")

    found = tree.callee("story", 1)

    assert found is not None
    assert found.name == "story"


def test_a_resolved_tree_answers_none_for_a_callee_it_does_not_hold() -> None:
    assert fixtures.tree("epic").callee("story", 2) is None


def test_a_resolved_tree_pins_the_root_first_then_the_callees_in_walk_order() -> None:
    tree = fixtures.tree("initiative")

    pinned = [(ref.name, ref.version) for ref in tree.pinned_versions()]

    assert pinned == [("initiative", 1), ("epic", 1), ("story", 1)]


def test_a_root_with_no_callees_pins_only_itself() -> None:
    assert len(fixtures.tree("repo-init").pinned_versions()) == 1


def test_a_resolved_tree_is_frozen() -> None:
    tree = fixtures.tree("epic")

    with pytest.raises(AttributeError):
        tree.callees = ()  # type: ignore[misc]


# --- the plan ---------------------------------------------------------------------------------


def test_a_plan_carries_the_commit_it_was_read_at_and_one_entry_per_list_file() -> None:
    plan = Plan(plan_ref="abc", plan_refs={"docs/stories.yaml": "abc"}, rows=())

    assert plan.plan_ref == "abc"
    assert plan.plan_refs == {"docs/stories.yaml": "abc"}
    assert plan.rows == ()


def test_a_plan_is_frozen() -> None:
    plan = Plan(plan_ref="abc", plan_refs={}, rows=())

    with pytest.raises(AttributeError):
        plan.plan_ref = "other"  # type: ignore[misc]


# --- the route the walker finds before the plan is numbered ---------------------------------


def test_a_found_redispatch_carries_the_target_as_a_path_and_its_own_provenance() -> None:
    """`seq` does not exist until the walk is over, so the walker records the path."""
    found = Redispatched(
        target_path="stories[0].build", max=1, template="story", version=1, line=42
    )

    assert (found.target_path, found.max) == ("stories[0].build", 1)
    assert (found.template, found.version, found.line) == ("story", 1, 42)


def test_a_found_redispatch_is_frozen() -> None:
    found = Redispatched(target_path="a", max=1, template="t", version=1, line=1)

    with pytest.raises(AttributeError):
        found.target_path = "b"  # type: ignore[misc]


def test_the_resolved_keys_are_the_field_names_the_executor_constructs_from() -> None:
    """4.7 builds `Redispatch(**with_resolved["on_fail"])`, so the keys are its fields."""
    assert {REDISPATCH_TARGET_SEQ, REDISPATCH_MAX} == set(Redispatch.model_fields)
