"""`on_fail {redispatch, max, consult}` on a `run` row (story 1-6, spine AD-22, 2026-11-02):
the shape checks, the parsed block and the block a planned row carries under `on_fail`.

Fixture templates only (hard rule 6): nothing here reads a shipped file."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.templates import on_fail
from orchestrator.application.templates.model import (
    BAD_REDISPATCH,
    INVALID_CONSULT_ON,
    INVALID_ON_FAIL,
    INVALID_TIMEOUT,
    INVALID_VALUE,
    MISSING_KEY,
    UNKNOWN_KEY,
    ConsultDecl,
    Step,
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

HEADER = """name: verifying
version: 1
inputs:
  project:      { type: project,    required: true }
  repository:   { type: repository, required: true }
  base_branch:  { type: string,     required: true }
  senior_model: { type: string,     required: false }
  senior_min:   { type: number,     required: false, default: 25 }
steps:
  - id: work
    uses: agent
    with: { harness: claude, prompt: "Do the work." }
    gate: liveness
  - id: verify
    run: make test
    gate: deterministic
    on_fail:
      redispatch: work
      max: 2
"""

DISPATCH = "Run {skill}; the command {command} exited {code}; write {decision}."
CONSULT = f"""      consult:
        model: "{{{{senior_model}}}}"
        skill: senior-consult
        timeout_min: "{{{{senior_min}}}}"
        prompts:
          dispatch: "{DISPATCH}"
          answer: 'Senior on "{{condition}}": {{answer}}'
"""

#: The line `on_fail:` and the line `consult:` sit on in `HEADER` and `HEADER + CONSULT`.
ON_FAIL_LINE = 17
CONSULT_LINE = 20
MAX = 2


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


def verify_route(plan: Plan) -> Any:
    return next(row for row in plan.rows if row.path == "verify").with_resolved["on_fail"]


def verify_step(text: str) -> Step:
    result = validate(text, templates=FakeTemplateVersionRepository([]))
    assert result.template is not None, result.errors
    step = result.template.steps[1]
    assert isinstance(step, Step)
    return step


# ── the shape ────────────────────────────────────────────────────────────────


def test_a_redispatch_with_a_consult_validates_and_parses() -> None:
    step = verify_step(HEADER + CONSULT)

    assert (step.redispatch, step.redispatch_max) == ("work", MAX)
    assert step.redispatch_consult == ConsultDecl(
        line=CONSULT_LINE,
        model="{{senior_model}}",
        harness=None,
        skill="senior-consult",
        on=("verify_failed",),
        timeout_min="{{senior_min}}",
        prompt_dispatch=DISPATCH,
        prompt_answer='Senior on "{condition}": {answer}',
    )


def test_a_redispatch_without_a_consult_parses_none() -> None:
    assert verify_step(HEADER).redispatch_consult is None


def test_a_plain_on_fail_parses_no_consult() -> None:
    plain = "    on_fail: fail\n"
    text = HEADER.replace("    on_fail:\n      redispatch: work\n      max: 2\n", plain)

    assert verify_step(text).redispatch_consult is None
    assert verify_step(text).on_fail == "fail"


def test_the_stop_may_be_named_and_only_as_verify_failed() -> None:
    named = HEADER + CONSULT.replace(
        "        skill: senior-consult\n",
        "        skill: senior-consult\n        on: [verify_failed]\n",
    )

    assert errors_of(named) == []
    assert verify_step(named).redispatch_consult is not None


@pytest.mark.parametrize("stop", ["[blocked]", "[]", "verify_failed"])
def test_any_other_stop_is_an_invalid_consult_on(stop: str) -> None:
    text = HEADER + CONSULT.replace(
        "        skill: senior-consult\n", f"        skill: senior-consult\n        on: {stop}\n"
    )

    assert errors_of(text) == [(CONSULT_LINE + 3, INVALID_CONSULT_ON)]


@pytest.mark.parametrize(
    ("needle", "replacement", "expected"),
    [
        ('        model: "{{senior_model}}"\n', "", [(CONSULT_LINE, MISSING_KEY)]),
        ("        skill: senior-consult\n", "", [(CONSULT_LINE, MISSING_KEY)]),
        (f'          dispatch: "{DISPATCH}"\n', "", [(CONSULT_LINE + 4, MISSING_KEY)]),
        (
            "        skill: senior-consult\n",
            "        skill: senior-consult\n        extra: 1\n",
            [(CONSULT_LINE + 3, UNKNOWN_KEY)],
        ),
        (
            '        timeout_min: "{{senior_min}}"\n',
            "        timeout_min: 0\n",
            [(CONSULT_LINE + 3, INVALID_TIMEOUT)],
        ),
        (
            "        skill: senior-consult\n",
            "        skill: [a]\n",
            [(CONSULT_LINE + 2, INVALID_VALUE)],
        ),
    ],
    ids=["no model", "no skill", "no dispatch", "unknown sub-key", "bad timeout", "bad skill"],
)
def test_a_malformed_consult_names_its_line(
    needle: str, replacement: str, expected: list[tuple[int, str]]
) -> None:
    assert errors_of(HEADER + CONSULT.replace(needle, replacement)) == expected


def test_a_consult_that_is_not_a_mapping_is_an_invalid_value() -> None:
    assert errors_of(HEADER + "      consult: senior\n") == [(CONSULT_LINE, INVALID_VALUE)]


def test_a_consult_on_a_row_that_is_not_a_run_row_is_an_invalid_on_fail() -> None:
    other = '  - id: other\n    uses: agent\n    with: { harness: claude, prompt: "x" }\n'
    text = HEADER + other + "    gate: liveness\n    on_fail:\n      redispatch: work\n"
    text += "      max: 1\n" + CONSULT

    assert errors_of(text) == [(ON_FAIL_LINE + 7, INVALID_ON_FAIL)]


@pytest.mark.parametrize(
    ("needle", "replacement", "reason"),
    [
        ("redispatch: work", "redispatch: nowhere", BAD_REDISPATCH),
        ("max: 2", "max: 0", INVALID_ON_FAIL),
        ("max: 2\n", "max: 2\n      extra: 1\n", INVALID_ON_FAIL),
        ("      redispatch: work\n      max: 2\n", "      redispatch: work\n", INVALID_ON_FAIL),
        ("      redispatch: work\n      max: 2\n", "      {}\n", INVALID_ON_FAIL),
        ("on_fail:\n      redispatch: work\n      max: 2\n", "on_fail: nope\n", INVALID_ON_FAIL),
    ],
    ids=["unknown target", "zero bound", "unknown key", "no bound", "empty", "unknown action"],
)
def test_the_older_on_fail_shapes_keep_their_checks(
    needle: str, replacement: str, reason: str
) -> None:
    assert errors_of(HEADER.replace(needle, replacement)) == [(ON_FAIL_LINE, reason)]


def test_a_step_without_on_fail_is_clean() -> None:
    result = validate(
        HEADER.split("    on_fail:", maxsplit=1)[0], templates=FakeTemplateVersionRepository([])
    )

    assert result.errors == ()
    assert on_fail.ON_FAIL_KEY == "on_fail"


# ── the plan ─────────────────────────────────────────────────────────────────


def test_a_named_senior_model_plans_the_block_under_on_fail() -> None:
    route = verify_route(planned(HEADER + CONSULT, senior_model="opus-senior"))

    assert route["max"] == MAX
    assert route["consult"] == {
        "model": "opus-senior",
        "harness": "",
        "skill": "senior-consult",
        "on": ["verify_failed"],
        "timeout_min": 25,
        "prompts": {"dispatch": DISPATCH, "answer": 'Senior on "{condition}": {answer}'},
    }


def test_a_blank_senior_model_plans_a_redispatch_with_no_consult() -> None:
    for values in ({"senior_model": ""}, {}):
        route = verify_route(planned(HEADER + CONSULT, **values))

        assert set(route) == {"target_seq", "max"}


def test_a_redispatch_that_declared_no_consult_plans_exactly_as_before() -> None:
    assert set(verify_route(planned(HEADER, senior_model="m"))) == {"target_seq", "max"}


def test_a_timeout_that_is_not_a_count_refuses_the_plan() -> None:
    text = HEADER.replace("type: number,     required: false, default: 25", "type: string")

    with pytest.raises(PlanError) as refused:
        planned(text + CONSULT, senior_model="m", senior_min="soon")

    assert refused.value.reason == BAD_MINUTES
