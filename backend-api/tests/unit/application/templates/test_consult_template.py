"""The `consult` key on an `agent` row (story 1-4, spine AD-22, 2026-11-02): its shape checks,
and the planned block a row carries — only when the resolved senior model is non-empty.

Fixture templates only (hard rule 6): nothing here reads a shipped file."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.templates.agent_row import CONSULT_KEY
from orchestrator.application.templates.consult import plan_consult
from orchestrator.application.templates.lines import load_with_lines
from orchestrator.application.templates.model import (
    INVALID_CONSULT_ON,
    INVALID_TIMEOUT,
    INVALID_VALUE,
    MISSING_KEY,
    UNKNOWN_KEY,
    ConsultDecl,
)
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import (
    BAD_MINUTES,
    Plan,
    PlanError,
    ResolvedTree,
)
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

HEADER = """name: consulting
version: 1
inputs:
  project:      { type: project,    required: true }
  repository:   { type: repository, required: true }
  base_branch:  { type: string,     required: true }
  harness:      { type: enum, values: [claude, codex, local], default: claude }
  senior_model: { type: string,     required: false }
  senior_min:   { type: number,     required: false, default: 25 }
steps:
  - id: work
    uses: agent
    with: { harness: "{{harness}}", prompt: "Do the work." }
    gate: liveness
"""

CONSULT = """    consult:
      model: "{{senior_model}}"
      skill: senior-consult
      on: [blocked]
      timeout_min: "{{senior_min}}"
      prompts:
        dispatch: "Run {skill} on {condition}; write {decision}."
        answer: 'Senior to "{condition}": {answer}'
"""

#: The line `consult:` sits on in `HEADER + CONSULT`.
CONSULT_LINE = 15


def errors_of(text: str) -> list[tuple[int, str]]:
    result = validate(text, templates=FakeTemplateVersionRepository([]))
    return [(error.line, error.reason) for error in result.errors]


def planned(text: str, **values: Any) -> Plan:
    result = validate(text, templates=FakeTemplateVersionRepository([]))
    assert result.template is not None, result.errors
    return plan_run(
        ResolvedTree(root=result.template),
        fixtures.inputs(values=values),
        git=FakeGit(refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA}, files={}, listings={}),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )


def work_row(plan: Plan) -> dict[str, Any]:
    return next(row for row in plan.rows if row.path == "work").with_resolved


# ── the shape ────────────────────────────────────────────────────────────────


def test_a_complete_consult_validates_and_parses() -> None:
    result = validate(HEADER + CONSULT, templates=FakeTemplateVersionRepository([]))

    assert result.errors == ()
    assert result.template is not None
    agent = result.template.steps[0].agent  # type: ignore[union-attr]
    assert agent is not None
    assert agent.consult == ConsultDecl(
        line=CONSULT_LINE,
        model="{{senior_model}}",
        harness=None,
        skill="senior-consult",
        on=("blocked",),
        timeout_min="{{senior_min}}",
        prompt_dispatch="Run {skill} on {condition}; write {decision}.",
        prompt_answer='Senior to "{condition}": {answer}',
    )


def test_a_row_without_a_consult_parses_none() -> None:
    result = validate(HEADER, templates=FakeTemplateVersionRepository([]))

    assert result.template is not None
    assert result.template.steps[0].agent.consult is None  # type: ignore[union-attr]


def test_a_consult_on_a_row_that_is_not_an_agent_is_an_unknown_key() -> None:
    text = """name: shell-consult
version: 1
steps:
  - id: verify
    run: make test
    gate: deterministic
    consult: { model: m, skill: s, on: [blocked] }
"""

    assert errors_of(text) == [(7, UNKNOWN_KEY)]


@pytest.mark.parametrize(
    ("needle", "replacement", "expected"),
    [
        ('      model: "{{senior_model}}"\n', "", [(CONSULT_LINE, MISSING_KEY)]),
        ("      skill: senior-consult\n", "", [(CONSULT_LINE, MISSING_KEY)]),
        (
            '        dispatch: "Run {skill} on {condition}; write {decision}."\n',
            "",
            [(CONSULT_LINE + 5, MISSING_KEY)],
        ),
        (
            "        answer: 'Senior to \"{condition}\": {answer}'\n",
            "",
            [(CONSULT_LINE + 5, MISSING_KEY)],
        ),
        ("      on: [blocked]\n", "      on: [budget]\n", [(CONSULT_LINE + 3, INVALID_CONSULT_ON)]),
        ("      on: [blocked]\n", "      on: []\n", [(CONSULT_LINE + 3, INVALID_CONSULT_ON)]),
        ("      on: [blocked]\n", "      on: blocked\n", [(CONSULT_LINE + 3, INVALID_CONSULT_ON)]),
        ("      on: [blocked]\n", "", [(CONSULT_LINE, MISSING_KEY)]),
        (
            "      skill: senior-consult\n",
            "      skill: [a]\n",
            [(CONSULT_LINE + 2, INVALID_VALUE)],
        ),
        (
            "      skill: senior-consult\n",
            "      skill: senior-consult\n      harness: 3\n",
            [(CONSULT_LINE + 3, INVALID_VALUE)],
        ),
        (
            "      skill: senior-consult\n",
            "      skill: senior-consult\n      extra: 1\n",
            [(CONSULT_LINE + 3, UNKNOWN_KEY)],
        ),
        (
            '        dispatch: "Run {skill} on {condition}; write {decision}."\n',
            '        dispatch: "x"\n        halt: "y"\n',
            [(CONSULT_LINE + 7, UNKNOWN_KEY)],
        ),
        (
            '        dispatch: "Run {skill} on {condition}; write {decision}."\n',
            "        dispatch: [x]\n",
            [(CONSULT_LINE + 6, INVALID_VALUE)],
        ),
        (
            '      timeout_min: "{{senior_min}}"\n',
            "      timeout_min: 0\n",
            [(CONSULT_LINE + 4, INVALID_TIMEOUT)],
        ),
    ],
    ids=[
        "no model",
        "no skill",
        "no dispatch prompt",
        "no answer prompt",
        "another stop kind",
        "no stop kind",
        "on not a list",
        "no on",
        "skill not text",
        "harness not text",
        "unknown sub-key",
        "unknown prompt",
        "prompt not text",
        "bad timeout",
    ],
)
def test_a_malformed_consult_names_its_line(
    needle: str, replacement: str, expected: list[tuple[int, str]]
) -> None:
    text = HEADER + CONSULT.replace(needle, replacement)

    assert errors_of(text) == expected


def test_a_consult_that_is_not_a_mapping_is_an_invalid_value() -> None:
    assert errors_of(HEADER + "    consult: senior\n") == [(CONSULT_LINE, INVALID_VALUE)]


def test_a_consult_without_prompts_is_a_missing_key() -> None:
    text = HEADER + CONSULT.split("      prompts:\n", maxsplit=1)[0]

    assert errors_of(text) == [(CONSULT_LINE, MISSING_KEY)]


def test_prompts_that_are_not_a_mapping_are_an_invalid_value() -> None:
    text = HEADER + CONSULT.split("      prompts:\n", maxsplit=1)[0] + "      prompts: none\n"

    assert errors_of(text) == [(CONSULT_LINE + 5, INVALID_VALUE)]


# ── the plan ─────────────────────────────────────────────────────────────────


def test_a_named_senior_model_plans_the_consult_block() -> None:
    row = work_row(planned(HEADER + CONSULT, senior_model="opus-senior"))

    assert row[CONSULT_KEY] == {
        "model": "opus-senior",
        "harness": "",
        "skill": "senior-consult",
        "on": ["blocked"],
        "timeout_min": 25,
        "prompts": {
            "dispatch": "Run {skill} on {condition}; write {decision}.",
            "answer": 'Senior to "{condition}": {answer}',
        },
    }


def test_a_blank_senior_model_plans_no_consult() -> None:
    assert CONSULT_KEY not in work_row(planned(HEADER + CONSULT, senior_model=""))
    assert CONSULT_KEY not in work_row(planned(HEADER + CONSULT))


def test_a_declared_harness_and_a_literal_timeout_are_planned_as_written() -> None:
    text = HEADER + CONSULT.replace(
        '      timeout_min: "{{senior_min}}"\n', "      harness: codex\n      timeout_min: 15\n"
    )

    row = work_row(planned(text, senior_model="m"))

    assert (row[CONSULT_KEY]["harness"], row[CONSULT_KEY]["timeout_min"]) == ("codex", 15)


def test_a_row_that_declared_no_consult_plans_none() -> None:
    assert plan_consult(None, {}) is None


def test_a_consult_with_no_timeout_plans_none() -> None:
    text = HEADER + CONSULT.replace('      timeout_min: "{{senior_min}}"\n', "")

    assert work_row(planned(text, senior_model="m"))[CONSULT_KEY]["timeout_min"] is None


def test_a_timeout_input_bound_empty_plans_none() -> None:
    text = HEADER.replace(", default: 25", "") + CONSULT

    assert work_row(planned(text, senior_model="m"))[CONSULT_KEY]["timeout_min"] is None


def test_a_timeout_that_is_not_a_count_refuses_the_plan() -> None:
    text = HEADER.replace("type: number,     required: false, default: 25", "type: string")

    with pytest.raises(PlanError) as refused:
        planned(text + CONSULT, senior_model="m", senior_min="soon")

    assert refused.value.reason == BAD_MINUTES


# ── the loader ───────────────────────────────────────────────────────────────


def test_a_plain_on_key_is_text_and_a_plain_on_value_stays_a_bool() -> None:
    loaded = load_with_lines("on: [blocked]\nyes: 1\n'no': 2\nflag: on\n")

    assert loaded.root is not None
    assert dict(loaded.root) == {"on": ["blocked"], "yes": 1, "no": 2, "flag": True}
    assert loaded.root.key_lines["on"] == 1
