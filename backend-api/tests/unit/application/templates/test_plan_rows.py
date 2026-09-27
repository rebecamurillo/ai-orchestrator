"""The walker's rules, on Templates written for the rule rather than for the product.

The four shipped files are checked in `test_plan_shipped.py`; what is here is everything
they do not happen to contain — a step nobody gated, a call at the top level, a pause
*before* an item, a shell step whose command resolves to nothing, and the two shapes a
validated file can never hold but a caller can still hand the walker.

`plan_run` is the entry point in every case, because a rule that only holds when the walker
is driven by hand is not a rule about plans.
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.dto import RepositorySnapshot
from orchestrator.application.graph import UNVALIDATED
from orchestrator.application.steps import KIND_META, SHELL_KIND
from orchestrator.application.templates.expressions import ENTITY_FIELDS
from orchestrator.application.templates.model import ForEach, ParsedTemplate, Step
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import (
    CALLEE_NOT_RESOLVED,
    DUPLICATE_ROW_PATH,
    ON_FAIL_KEY,
    REASON_NO_CHECKPOINT,
    REASON_NO_COMMAND,
    REASON_NO_QUALITY_GATE,
    REDISPATCH_TARGET_NOT_PLANNED,
    Plan,
    PlanError,
    ResolvedTree,
)
from orchestrator.application.templates.rows import working_branch
from orchestrator.application.templates.skip_reason import QUALITY_GATE_FIELD
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateVersion
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

REF = fixtures.BASE_SHA
FOLDER = "docs/epic-1"
THINGS_PATH = f"{FOLDER}/things.yaml"

#: The timeout the `timed` step below declares for itself.
DECLARED_TIMEOUT_MIN = 7

HEADER = """name: {name}
version: 1
inputs:
  project:     {{ type: project,    required: true }}
  repository:  {{ type: repository, required: true }}
  base_branch: {{ type: string,     required: true }}
  spec_folder: {{ type: path,       required: true }}
  extra:       {{ type: string,     required: false }}
  harness:     {{ type: enum, values: [claude, codex, local], default: claude }}
steps:
"""

LEAF = """name: leaf
version: 1
inputs:
  project: { type: project, required: true }
steps:
  - id: sync
    uses: git.sync
    gate: deterministic
"""

GATES = (
    HEADER.format(name="gates")
    + """  - id: loose
    uses: git.sync
  - id: strict
    uses: git.sync
    gate: liveness
  - id: hold
    uses: checkpoint
    gate: human
"""
)

CALLER = (
    HEADER.format(name="caller")
    + """  - id: sub
    uses: template
    with:
      name: leaf
      version: 1
      inputs:
        project: "{{project}}"
"""
)

PAUSED = (
    HEADER.format(name="paused")
    + """  - id: things
    for_each: "{{spec_folder}}/things.yaml"
    as: thing
    pause_before_item_when: "thing.review"
    steps:
      - id: work
        uses: agent
        with: { harness: "{{harness}}" }
        expect: { status_in: [done] }
        retry: { max: 2, prompt: "again for {{thing.id}}" }
        pause_when: "thing.review"
        gate: liveness
"""
)

COMMANDS = (
    HEADER.format(name="commands")
    + """  - id: baseline
    run: "{{repository.quality_gate_command}}"
    gate: deterministic
  - id: extras
    run: "{{extra}}"
    gate: deterministic
  - id: timed
    run: "echo hi"
    timeout_min: 7
    gate: deterministic
  - id: bare
    uses: shell
    gate: deterministic
  - id: spaces
    run: "{{extra}} "
    gate: deterministic
  - id: soft
    run: "echo hi"
    on_fail: continue
    gate: deterministic
  - id: loud
    run: "echo hi"
    on_fail: escalate
    gate: deterministic
"""
)

#: `bare` keeps today's behaviour exactly — no `when` key, always a live human gate;
#: `conditional` declares `with {when}` against the shared `extra` input, so binding it
#: to nothing, `""`, `False` or a truthy string exercises every branch of the plan-time
#: rule (multi-repo initiative S5, spine AD-7 amendment, 2026-09-23).
CHECKPOINTS = (
    HEADER.format(name="checkpoints")
    + """  - id: bare
    uses: checkpoint
    gate: human
  - id: conditional
    uses: checkpoint
    with: { when: "{{extra}}" }
    gate: human
"""
)

BRANCHLESS = (
    HEADER.format(name="branchless")
    + """  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{extra}}" }
    gate: deterministic
"""
)

#: A top-level `git.push` names a branch and checks nothing out: no working branch.
PUSH_ONLY = (
    HEADER.format(name="push-only")
    + """  - id: push
    uses: git.push
    with: { branch: "{{extra}}" }
    gate: deterministic
"""
)

#: A top-level step whose id is the one the plan check already takes: two rows, one path.
#: The validator reserves `before` and `after` inside a paused loop but not this one, since
#: the plan check is a row no Template can see.
COLLIDING = (
    HEADER.format(name="colliding")
    + """  - id: plan
    uses: git.sync
    gate: deterministic
"""
)

#: A redispatch the validator accepts and no frame can honour: `keys.py` keeps one flat set
#: of earlier `agent` steps for the whole file, so a step inside the loop may name one
#: outside it — and `things[0].build` is not a row.
CROSS_FRAME = (
    HEADER.format(name="cross-frame")
    + """  - id: build
    uses: agent
    with: { harness: "{{harness}}" }
    gate: liveness
  - id: things
    for_each: "{{spec_folder}}/things.yaml"
    as: thing
    steps:
      - id: verify
        run: "echo hi"
        on_fail: { redispatch: build, max: 1 }
        gate: deterministic
"""
)

THINGS = """
- id: t1
  review: true
- id: t2
"""


def parsed(text: str, *stored: TemplateVersion) -> ParsedTemplate:
    result = validate(text, templates=FakeTemplateVersionRepository(list(stored)))

    assert result.template is not None, result.errors
    return result.template


def leaf_version() -> TemplateVersion:
    return TemplateVersion(name="leaf", version=1, yaml=LEAF, hash="sha")


def planned(
    text: str,
    *,
    callees: tuple[ParsedTemplate, ...] = (),
    git: FakeGit | None = None,
    values: dict[str, Any] | None = None,
    repository: RepositorySnapshot = fixtures.REPOSITORY,
) -> Plan:
    tree = ResolvedTree(root=parsed(text, leaf_version()), callees=callees)
    return plan_run(
        tree,
        fixtures.inputs(values={"spec_folder": FOLDER, **(values or {})}, repository=repository),
        git=git or FakeGit(refs={"main": REF}, files={}, listings={}),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )


def paths(plan: Plan) -> list[str]:
    return [row.path for row in plan.rows]


def row(plan: Plan, path: str) -> Any:
    return next(entry for entry in plan.rows if entry.path == path)


# --- gates ----------------------------------------------------------------------------------


def test_a_step_that_declares_no_gate_is_unvalidated_and_never_its_kinds_default() -> None:
    plan = planned(GATES)

    assert row(plan, "loose").gate == UNVALIDATED
    assert KIND_META["git.sync"].gate_default != UNVALIDATED


def test_a_step_that_declares_a_gate_carries_the_one_it_declared() -> None:
    assert row(planned(GATES), "strict").gate == "liveness"


def test_the_first_row_of_every_plan_is_the_plan_check() -> None:
    plan = planned(GATES)

    assert (plan.rows[0].seq, plan.rows[0].path, plan.rows[0].label) == (1, "plan", "plan")
    assert (plan.rows[0].kind, plan.rows[0].gate) == ("plan.check", "deterministic")
    assert plan.rows[0].status == "planned"


def test_seq_is_dense_from_one() -> None:
    plan = planned(GATES)

    assert [entry.seq for entry in plan.rows] == list(range(1, len(plan.rows) + 1))


def test_a_top_level_row_has_no_frame_and_no_story() -> None:
    entry = row(planned(GATES), "strict")

    assert (entry.frame, entry.story_id) == (None, None)


def test_a_step_a_template_declared_as_a_checkpoint_is_timed_by_nothing() -> None:
    """`checkpoint` is the one kind with no timeout of its own, declared or defaulted."""
    assert row(planned(GATES), "hold").with_resolved == {}


# --- calls ------------------------------------------------------------------------------------


def test_a_call_at_the_top_level_contributes_its_own_id_to_the_path() -> None:
    plan = planned(CALLER, callees=(parsed(LEAF),))

    assert paths(plan) == ["plan", "sub.sync"]


def test_a_call_is_not_a_row_of_its_own() -> None:
    plan = planned(CALLER, callees=(parsed(LEAF),))

    assert all(entry.kind != "template" for entry in plan.rows)


def test_a_call_whose_callee_the_tree_does_not_hold_is_a_plan_error() -> None:
    with pytest.raises(PlanError) as raised:
        planned(CALLER)

    assert raised.value.reason == CALLEE_NOT_RESOLVED
    assert raised.value.item == "leaf@1"
    assert raised.value.template == "caller"


# --- loops ------------------------------------------------------------------------------------


def things_git() -> FakeGit:
    return FakeGit(refs={"main": REF}, files={(REF, THINGS_PATH): THINGS}, listings={})


def test_a_loop_over_any_other_file_indexes_its_items_and_labels_them_by_the_as_name() -> None:
    plan = planned(PAUSED, git=things_git())

    assert paths(plan) == ["plan", "things[0].before", "things[0].work", "things[1].work"]
    assert row(plan, "things[1].work").label == "thing 2 · work"


def test_a_pause_before_an_item_is_the_first_row_of_that_items_frame() -> None:
    plan = planned(PAUSED, git=things_git())
    before = row(plan, "things[0].before")

    assert (before.kind, before.gate, before.status) == ("checkpoint", "human", "planned")
    assert before.label == "thing 1 · before"


def test_an_item_whose_pause_field_is_absent_gets_no_checkpoint_row() -> None:
    assert "things[1].before" not in paths(planned(PAUSED, git=things_git()))


def test_a_row_inside_a_loop_carries_the_frame_it_is_in() -> None:
    assert row(planned(PAUSED, git=things_git()), "things[0].work").frame == "things[0]"


def test_a_loop_that_is_not_over_stories_carries_no_story_id() -> None:
    assert row(planned(PAUSED, git=things_git()), "things[0].work").story_id is None


def test_a_checkpoint_row_carries_no_timeout_because_nothing_times_a_person() -> None:
    assert row(planned(PAUSED, git=things_git()), "things[0].before").with_resolved == {}


# --- the agent extras ----------------------------------------------------------------------------


def test_an_agent_row_carries_the_pause_flag_rather_than_a_row_of_its_own() -> None:
    plan = planned(PAUSED, git=things_git())

    assert row(plan, "things[0].work").with_resolved["spec_checkpoint"] is True
    assert row(plan, "things[1].work").with_resolved["spec_checkpoint"] is False


def test_an_agent_row_carries_its_expect_and_retry_resolved() -> None:
    resolved = row(planned(PAUSED, git=things_git()), "things[0].work").with_resolved

    # Revised 2026-09-27 (Operator decision: declarable result contract) — the routing
    # lists ride the same dict, empty when the file declares none.
    assert resolved["expect"] == {
        "files": [],
        "status_in": ["done"],
        "success": [],
        "blocked": [],
        "checkpoint": [],
        "misconfigured_when": [],
    }
    assert resolved["retry"] == {"max": 2, "prompt": "again for t1", "resume_session": True}


def test_an_agent_row_carries_no_timeout_when_the_step_declares_none() -> None:
    """Operator revision 2026-09-15: the agent kind's `timeout_default_min` is now `None`
    (no wall-clock deadline by default); stall detection replaced the hard kill."""
    resolved = row(planned(PAUSED, git=things_git()), "things[0].work").with_resolved

    assert "timeout_min" not in resolved
    assert KIND_META["agent"].timeout_default_min is None
    assert KIND_META["agent"].stall_default_min == 30  # noqa: PLR2004
    assert resolved["stall_min"] == 30  # noqa: PLR2004


# --- the skipped rules ----------------------------------------------------------------------------


def test_a_shell_step_whose_command_is_the_quality_gate_the_repository_has_not_is_skipped() -> None:
    plan = planned(COMMANDS, repository=fixtures.NO_QUALITY_GATE)
    entry = row(plan, "baseline")

    assert (entry.status, entry.reason) == ("skipped", REASON_NO_QUALITY_GATE)


def test_a_shell_step_whose_command_resolves_to_nothing_else_is_skipped_as_no_command() -> None:
    entry = row(planned(COMMANDS), "extras")

    assert (entry.status, entry.reason) == ("skipped", REASON_NO_COMMAND)


def test_a_shell_step_that_declares_no_command_at_all_is_skipped_the_same_way() -> None:
    entry = row(planned(COMMANDS), "bare")

    assert (entry.status, entry.reason) == ("skipped", REASON_NO_COMMAND)


def test_the_quality_gate_field_the_reason_is_decided_by_is_the_validators_own() -> None:
    assert QUALITY_GATE_FIELD in ENTITY_FIELDS["repository"]


def test_a_shell_step_with_a_command_is_planned() -> None:
    entry = row(planned(COMMANDS), "baseline")

    assert (entry.status, entry.reason) == ("planned", None)
    assert entry.with_resolved["command"] == "make check"


def test_a_step_that_declares_a_timeout_keeps_the_one_it_declared() -> None:
    assert row(planned(COMMANDS), "timed").with_resolved["timeout_min"] == DECLARED_TIMEOUT_MIN


def test_a_step_that_declares_none_takes_its_kinds_default() -> None:
    resolved = row(planned(COMMANDS), "baseline").with_resolved

    assert resolved["timeout_min"] == KIND_META[SHELL_KIND].timeout_default_min


# --- checkpoint `when` (S5) ----------------------------------------------------------------


def test_a_checkpoint_with_no_when_key_keeps_todays_behaviour_and_is_always_planned() -> None:
    entry = row(planned(CHECKPOINTS), "bare")

    assert (entry.status, entry.reason) == ("planned", None)


def test_a_checkpoint_whose_when_is_unbound_resolves_falsy_and_is_skipped() -> None:
    """The unbound-optional-input finding (S5): `{{extra}}` resolves to `""` rather than
    erroring, the same rule that turns an unset command into a `skipped` shell row."""
    entry = row(planned(CHECKPOINTS), "conditional")

    assert (entry.status, entry.reason) == ("skipped", REASON_NO_CHECKPOINT)


def test_a_checkpoint_whose_when_resolves_to_an_empty_string_is_skipped() -> None:
    entry = row(planned(CHECKPOINTS, values={"extra": ""}), "conditional")

    assert (entry.status, entry.reason) == ("skipped", REASON_NO_CHECKPOINT)


def test_a_checkpoint_whose_when_is_bound_to_the_literal_false_is_skipped() -> None:
    """A whole-variable bind (no `.field`) passes a non-string value through raw
    (`substitute.py`'s own rule), so a caller handing a JSON `false` reaches here as the
    Python value, not the four characters `False`."""
    entry = row(planned(CHECKPOINTS, values={"extra": False}), "conditional")

    assert (entry.status, entry.reason) == ("skipped", REASON_NO_CHECKPOINT)


def test_a_checkpoint_whose_when_resolves_truthy_is_planned() -> None:
    entry = row(planned(CHECKPOINTS, values={"extra": "true"}), "conditional")

    assert (entry.status, entry.reason) == ("planned", None)
    assert entry.with_resolved["when"] == "true"


# --- the working branch ------------------------------------------------------------------------


def test_the_working_branch_is_the_first_branch_the_top_level_steps_name() -> None:
    template = parsed(fixtures.TEXTS["epic"], *_shipped_versions())

    assert working_branch(template, {"branch": "feat/x"}) == "feat/x"


def test_a_template_whose_top_level_names_no_branch_at_all_works_on_none() -> None:
    template = parsed(fixtures.TEXTS["initiative"], *_shipped_versions())

    assert working_branch(template, {}) is None


def test_a_branch_that_resolves_to_nothing_is_no_working_branch() -> None:
    """A Run whose branch input nobody filled works from the base, not from `origin/`."""
    assert working_branch(parsed(BRANCHLESS), {}) is None
    assert planned(BRANCHLESS).plan_ref == REF


def _shipped_versions() -> tuple[TemplateVersion, ...]:
    return tuple(fixtures.repository_of_versions().versions.values())


# --- the two shapes a validated file cannot hold -----------------------------------------------


def synthetic_loop(condition: str) -> ParsedTemplate:
    """A loop whose pause condition is not `<name>.<field>` — `validate()` refuses it."""
    return ParsedTemplate(
        line=1,
        name="synthetic",
        version=1,
        steps=(
            ForEach(
                line=2,
                id="things",
                source=f"{FOLDER}/things.yaml",
                as_name="thing",
                pause_after_item_when=condition,
                steps=(
                    Step(
                        line=3,
                        id="sync",
                        uses="git.sync",
                        meta=KIND_META["git.sync"],
                        gate="deterministic",
                    ),
                ),
            ),
        ),
    )


def plan_of(template: ParsedTemplate, git: FakeGit) -> Plan:
    return plan_run(
        ResolvedTree(root=template),
        fixtures.inputs(values={"spec_folder": FOLDER}),
        git=git,
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )


def test_a_pause_condition_that_is_not_a_field_of_the_item_pauses_at_nothing() -> None:
    plan = plan_of(synthetic_loop("nonsense"), things_git())

    assert paths(plan) == ["plan", "things[0].sync", "things[1].sync"]


def test_a_pause_condition_naming_a_truthy_field_still_pauses() -> None:
    plan = plan_of(synthetic_loop("thing.review"), things_git())

    assert paths(plan) == ["plan", "things[0].sync", "things[0].after", "things[1].sync"]


def test_a_step_id_written_with_underscores_reads_as_words_in_its_label() -> None:
    """No shipped id needs it — a slug has no `_` — but the label rule is the label rule."""
    template = ParsedTemplate(
        line=1,
        name="synthetic",
        version=1,
        steps=(
            Step(
                line=2,
                id="two_words",
                uses="git.sync",
                meta=KIND_META["git.sync"],
                gate="deterministic",
            ),
        ),
    )

    assert row(plan_of(template, FakeGit(refs={"main": REF})), "two_words").label == "two words"


def test_a_command_whose_expression_names_nothing_at_all_is_skipped_as_no_command() -> None:
    """`{{ }}` is `expression syntax` to the validator; the walker still has to answer."""
    template = ParsedTemplate(
        line=1,
        name="synthetic",
        version=1,
        steps=(
            Step(
                line=2,
                id="baseline",
                uses=SHELL_KIND,
                meta=KIND_META[SHELL_KIND],
                params=(("command", "{{ }}"),),
                gate="deterministic",
            ),
        ),
    )

    entry = row(plan_of(template, FakeGit(refs={"main": REF})), "baseline")

    assert (entry.status, entry.reason) == ("skipped", REASON_NO_COMMAND)


# --- the rules a review found nothing standing behind --------------------------------------------


def test_a_command_that_resolves_to_whitespace_is_as_empty_as_one_that_resolves_to_nothing() -> (
    None
):
    """A shell handed `" "` runs nothing and reports success — a green row nobody ran."""
    entry = row(planned(COMMANDS), "spaces")

    assert (entry.status, entry.reason) == ("skipped", REASON_NO_COMMAND)


def test_a_branch_a_push_names_is_not_the_branch_the_run_works_on() -> None:
    """Only the worktree decides the commit the plan is read at; a push names its target."""
    assert working_branch(parsed(PUSH_ONLY), {"extra": "release/x"}) is None


def test_a_template_that_only_pushes_plans_from_the_base_and_not_from_that_branch() -> None:
    other = "1111111111111111111111111111111111111111"
    git = FakeGit(refs={"main": REF, "release/x": other}, files={}, listings={})

    assert planned(PUSH_ONLY, git=git, values={"extra": "release/x"}).plan_ref == REF


def test_two_rows_that_would_answer_to_one_path_stop_the_plan() -> None:
    """`step_run` is stored unique on `(run_id, path)`, so this is a 422 and not a 500."""
    with pytest.raises(PlanError) as raised:
        planned(COLLIDING)

    assert raised.value.reason == DUPLICATE_ROW_PATH
    assert raised.value.item == "plan"


def test_a_run_value_cannot_replace_the_repository_the_run_was_created_from() -> None:
    """The snapshots are the Run's own; a Template input sharing a name is not them."""
    entry = row(planned(COMMANDS, values={"repository": "nonsense"}), "baseline")

    assert entry.with_resolved["command"] == fixtures.REPOSITORY.quality_gate_command


# --- how a failed row is routed ------------------------------------------------------------------


def test_a_continue_is_carried_as_the_word_the_template_wrote() -> None:
    assert row(planned(COMMANDS), "soft").with_resolved[ON_FAIL_KEY] == "continue"


def test_an_escalate_is_carried_even_though_it_is_the_default() -> None:
    """A file that said it means it; the executor never has to ask which of the two it is."""
    assert row(planned(COMMANDS), "loud").with_resolved[ON_FAIL_KEY] == "escalate"


def test_a_row_that_declared_no_routing_carries_none() -> None:
    assert ON_FAIL_KEY not in row(planned(COMMANDS), "timed").with_resolved


def test_a_redispatch_the_frame_cannot_honour_stops_the_plan() -> None:
    """The validator accepts this file: its earlier-agent set is flat over the whole file."""
    with pytest.raises(PlanError) as raised:
        planned(CROSS_FRAME, git=things_git())

    assert raised.value.reason == REDISPATCH_TARGET_NOT_PLANNED
    assert raised.value.item == "things[0].build"


def test_the_refusal_names_the_template_that_declared_the_route() -> None:
    with pytest.raises(PlanError) as raised:
        planned(CROSS_FRAME, git=things_git())

    assert (raised.value.template, raised.value.version) == ("cross-frame", 1)
    assert raised.value.line is not None
