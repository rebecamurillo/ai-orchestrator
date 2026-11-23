"""The `conversation` kind: registry row, validation, graph and planned row (epic 4 story 3).

Every template here is this test's own fixture, never a shipped `templates/*.yaml`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import yaml
from jsonschema import Draft202012Validator

from orchestrator.application.format_schemas import workflow_schema
from orchestrator.application.graph import build_run_graph, build_template_graph
from orchestrator.application.steps import KIND_META, KindMeta
from orchestrator.application.steps.conversation import ConversationExecutor
from orchestrator.application.steps.registry import executor_for
from orchestrator.application.templates import conversation, conversation_model
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import ResolvedTree
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.templates import FakeTemplateVersionRepository

NAMES = ("intake", "product", "ux", "tech")

HEAD = """name: talking
version: 1
{type}steps:
"""

STEP = """  - id: {name}
    uses: conversation
    role: {role}
    gate: human
    with: {{ step: {name}, skill: bmad-{name}, persona: Mary }}
    expect:
      files: {files}
      success: [{success}]
    writes: ["docs/{name}.md"]
    prompts:
      open: "Open {name}."
      close: "Close {name} as {{attempt_id}}."
{extra}"""


def document(  # noqa: PLR0913 — one keyword per thing a case varies
    *,
    type_line: str = "type: interactive\n",
    role: str = "plan",
    files: str = '["docs/{name}.md"]',
    success: str = "done",
    extra: str = "",
    names: tuple[str, ...] = NAMES,
) -> str:
    head = HEAD.format(type=type_line)
    return head + "".join(
        STEP.format(
            name=name,
            role=role,
            files=files.format(name=name),
            success=success,
            extra=extra,
        )
        for name in names
    )


def check(text: str):  # type: ignore[no-untyped-def]
    return validate(text, templates=FakeTemplateVersionRepository([]))


def reasons(text: str) -> list[str]:
    return [record.reason for record in check(text).errors]


# ── AC3 ──────────────────────────────────────────────────────────────────────


def test_the_registry_row() -> None:
    assert KIND_META["conversation"] == KindMeta(
        "human", None, frozenset({"skill", "persona", "step"})
    )
    assert isinstance(executor_for("conversation"), ConversationExecutor)


# ── AC1 ──────────────────────────────────────────────────────────────────────


def test_four_conversation_steps_validate_with_one_human_node_each() -> None:
    result = check(document())

    assert list(result.errors) == []
    assert result.template is not None
    graph = build_template_graph(result.template)
    nodes = {node.id: node for node in graph.nodes if node.id in NAMES}
    assert sorted(nodes) == sorted(NAMES)
    assert all(node.human for node in nodes.values())


def test_an_auto_template_refuses_each_step() -> None:
    for type_line in ("type: auto\n", ""):
        found = reasons(document(type_line=type_line))

        assert found == [f"step {name}: conversation needs type: interactive" for name in NAMES]


# ── AC2 ──────────────────────────────────────────────────────────────────────


def test_a_glob_is_not_a_literal_path() -> None:
    assert reasons(document(files='"*.md"', names=("intake",))) == [
        "step intake: expect.files is one literal path"
    ]
    assert reasons(document(files='["a/?.md"]', names=("intake",))) == [
        "step intake: expect.files is one literal path"
    ]


def test_one_literal_path_as_text_or_as_a_list_validates() -> None:
    assert list(check(document(files='"a/{name}.md"')).errors) == []
    assert list(check(document(files='["a/{name}.md"]')).errors) == []


def test_zero_or_two_paths_are_refused() -> None:
    for files in ("[]", '["a.md", "b.md"]', "7"):
        assert reasons(document(files=files, names=("intake",))) == [
            "step intake: expect.files is one literal path"
        ]


def test_expect_success_needs_one_word() -> None:
    assert reasons(document(success="", names=("intake",))) == [
        "step intake: expect.success needs one word"
    ]
    text = document(names=("intake",)).replace("      success: [done]\n", "")
    assert reasons(text) == ["step intake: expect.success needs one word"]


def test_the_close_prompt_must_exist_and_name_the_attempt() -> None:
    base = document(names=("intake",))
    missing = base.replace('      close: "Close intake as {attempt_id}."\n', "")
    unnamed = base.replace("{attempt_id}", "{x}")

    assert reasons(missing) == ["step intake: prompts.close is required"]
    assert reasons(unnamed) == ["step intake: prompts.close must name {attempt_id}"]


def test_the_open_prompt_is_required() -> None:
    text = document(names=("intake",)).replace('      open: "Open intake."\n', "")

    assert reasons(text) == ["step intake: prompts.open is required"]


def test_the_role_is_plan() -> None:
    assert reasons(document(role="implement", names=("intake",))) == [
        "step intake: role must be plan"
    ]
    text = document(names=("intake",)).replace("    role: plan\n", "")
    assert reasons(text) == ["step intake: role must be plan"]


def test_an_unknown_step_key_names_the_step_and_the_key() -> None:
    assert reasons(document(extra="    colour: red\n", names=("intake",))) == [
        "step intake: colour: unknown key"
    ]


def test_unknown_expect_and_prompts_keys_are_named() -> None:
    expect = document(names=("intake",)).replace(
        "      success: [done]\n", "      success: [done]\n      status_in: [done]\n"
    )
    prompts = document(names=("intake",)).replace(
        '      open: "Open intake."\n', '      open: "Open intake."\n      halt: "x"\n'
    )

    assert reasons(expect) == ["step intake: expect.status_in: unknown key"]
    assert reasons(prompts) == ["step intake: prompts.halt: unknown key"]


def test_with_keys_and_writes_are_checked() -> None:
    slug = document(names=("intake",)).replace("step: intake", "step: Intake Step")
    skill = document(names=("intake",)).replace("skill: bmad-intake", "skill: [a]")
    persona = document(names=("intake",)).replace("persona: Mary", "persona: [a]")
    writes = document(names=("intake",)).replace('writes: ["docs/intake.md"]', "writes: 3")

    assert reasons(slug) == ["step intake: with.step must be a slug"]
    assert reasons(skill) == ["step intake: with.skill is text"]
    assert reasons(persona) == ["step intake: with.persona is text"]
    assert reasons(writes) == ["step intake: writes is a list of text"]


def test_a_refusal_sits_at_the_offending_key() -> None:
    text = document(role="implement", names=("intake",))
    [record] = check(text).errors

    assert text.splitlines()[record.line - 1].strip() == "role: implement"


def test_a_missing_expect_or_prompts_block_is_refused_at_the_step() -> None:
    text = HEAD.format(type="type: interactive\n") + (
        "  - id: intake\n"
        "    uses: conversation\n"
        "    role: plan\n"
        "    with: { step: intake, skill: bmad-intake, persona: Mary }\n"
    )
    errors = check(text).errors

    assert sorted(record.reason for record in errors) == [
        "step intake: expect.files is one literal path",
        "step intake: expect.success needs one word",
        "step intake: prompts.close is required",
        "step intake: prompts.open is required",
    ]
    assert {text.splitlines()[record.line - 1].strip() for record in errors} == {"- id: intake"}


def test_a_step_in_a_loop_is_checked_too() -> None:
    text = """name: looped
version: 1
type: auto
inputs:
  items: { type: string }
steps:
  - id: each
    for_each: "{{items}}"
    as: item
    steps:
      - id: talk
        uses: conversation
"""
    assert "step talk: conversation needs type: interactive" in reasons(text)


# ── the planned row ──────────────────────────────────────────────────────────


def test_a_planned_conversation_row_carries_its_contract() -> None:
    parsed = check(document(files='"docs/{name}.md"', names=("intake",))).template
    assert parsed is not None

    plan = plan_run(
        ResolvedTree(root=parsed, callees=()),
        fixtures.inputs(),
        git=fixtures.repo_init_git(),
        base_dir=Path("/work/my-project/my-repo/base"),
        bmad_version=fixtures.BMAD_VERSION,
    )

    row = next(entry for entry in plan.rows if entry.kind == "conversation")
    resolved = row.with_resolved
    assert resolved["step"] == "intake"
    assert resolved["skill"] == "bmad-intake"
    assert resolved["persona"] == "Mary"
    assert resolved["expect"]["files"] == ["docs/intake.md"]
    assert resolved["expect"]["success"] == ["done"]
    assert resolved["writes"] == ["docs/intake.md"]
    assert resolved["prompts"] == {
        "open": "Open intake.",
        "close": "Close intake as {attempt_id}.",
    }


def test_the_parsed_extras_are_the_checkers_own_model() -> None:
    parsed = check(document(names=("intake",))).template
    assert parsed is not None
    step = parsed.steps[0]

    assert isinstance(step.conversation, conversation_model.ConversationExtras)  # type: ignore[union-attr]
    assert conversation.parse_conversation is not None


# ── review patches: the schema branch and the run graph agree with the validator ────────


def _schema_errors(text: str) -> list[str]:
    validator = Draft202012Validator(workflow_schema())
    return [error.message for error in validator.iter_errors(yaml.safe_load(text))]


def test_the_schema_accepts_what_the_validator_accepts() -> None:
    text = document()

    assert check(text).errors == ()
    assert _schema_errors(text) == []


def test_the_schema_refuses_what_the_validator_refuses_per_step() -> None:
    for text in (
        document(role="implement"),
        document().replace(", skill: bmad-intake", ""),
        document().replace("      success: [done]\n", "", 1),
    ):
        assert check(text).errors
        assert _schema_errors(text)


def test_a_conversation_row_is_human_in_the_run_graph_whatever_its_gate() -> None:
    run = Run(
        id=uuid4(),
        project_id=uuid4(),
        repository_id=uuid4(),
        template_name="talking",
        template_version=1,
        status="running",
        budget_usd=Decimal("10"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    conversation_row = StepRun(
        id=uuid4(),
        run_id=run.id,
        seq=1,
        path="intake",
        label="intake",
        kind="conversation",
        gate="deterministic",
        status="planned",
    )

    [node] = [
        node for node in build_run_graph([conversation_row], run).nodes if node.id == "intake"
    ]

    assert node.human
