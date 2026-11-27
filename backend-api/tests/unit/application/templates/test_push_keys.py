"""`git.push` `allow_default_branch` and `retry {max, sync_first}`: the key table, the parse and
the planned row (epic 8 story 3, AC12, AC13). Fixture files only; no shipped template is read."""

from __future__ import annotations

import pytest

from orchestrator.application.templates.keys import check_keys
from orchestrator.application.templates.model import (
    INVALID_VALUE,
    MISSING_KEY,
    UNKNOWN_KEY,
    ParsedTemplate,
)
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import ResolvedTree
from orchestrator.application.templates.push_keys import PUSH_DEFAULT_NEEDS_INTERACTIVE
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates import parsed, reasons
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

AUTO = "name: push\nversion: 1\n"
INTERACTIVE = "name: push\nversion: 1\ntype: interactive\n"
COMMIT = "  - id: c\n    uses: git.commit\n    gate: deterministic\n    with: {message: m}\n"


def push(*, allow: str = "", retry: str = "") -> str:
    text = "steps:\n  - id: p\n    uses: git.push\n    gate: deterministic\n    with:\n"
    text += "      branch: main\n"
    if allow:
        text += f"      allow_default_branch: {allow}\n"
    if retry:
        text += f"    retry: {retry}\n"
    return text


def template(text: str) -> ParsedTemplate:
    result = validate(text, templates=FakeTemplateVersionRepository([]))
    assert result.template is not None, result.errors
    return result.template


def check(head: str, body: str) -> list[str]:
    errors, _ = check_keys(parsed(head + body))
    return reasons(errors)


def test_the_default_branch_key_is_allowed_in_an_interactive_template() -> None:
    assert check(INTERACTIVE, push(allow="true")) == []


def test_the_default_branch_key_needs_an_interactive_template() -> None:
    assert check(AUTO, push(allow="true")) == [PUSH_DEFAULT_NEEDS_INTERACTIVE]
    assert check(AUTO + "type: auto\n", push(allow="true")) == [PUSH_DEFAULT_NEEDS_INTERACTIVE]


def test_a_false_default_branch_key_needs_nothing() -> None:
    assert check(AUTO, push(allow="false")) == []


def test_a_valid_retry_is_allowed() -> None:
    assert check(AUTO, push(retry="{max: 3, sync_first: true}")) == []
    assert check(AUTO, push(retry="{max: 1, sync_first: true}")) == []


@pytest.mark.parametrize(
    ("retry", "reason"),
    [
        ("{max: 4, sync_first: true}", INVALID_VALUE),
        ("{max: 0, sync_first: true}", INVALID_VALUE),
        ("{max: true, sync_first: true}", INVALID_VALUE),
        ("{max: '2', sync_first: true}", INVALID_VALUE),
        ("{max: 1, sync_first: false}", INVALID_VALUE),
        ("{max: 1}", MISSING_KEY),
        ("{sync_first: true}", MISSING_KEY),
        ("{max: 1, sync_first: true, prompt: x}", UNKNOWN_KEY),
        ("3", MISSING_KEY),
    ],
)
def test_a_malformed_retry_is_refused(retry: str, reason: str) -> None:
    assert reason in check(AUTO, push(retry=retry))


def test_retry_on_another_kind_is_an_unknown_key() -> None:
    body = COMMIT + "    retry: {max: 1, sync_first: true}\n"
    assert UNKNOWN_KEY in check(AUTO, "steps:\n" + body)


def test_a_push_without_the_keys_is_checked_by_nothing_here() -> None:
    assert check(AUTO, push()) == []


def test_a_planned_row_carries_the_retry_and_the_default_branch_key() -> None:
    text = INTERACTIVE + push(allow="true", retry="{max: 2, sync_first: true}")
    plan = plan_run(
        ResolvedTree(root=template(text), callees=()),
        fixtures.inputs(values={}),
        git=FakeGit(refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA}, files={}, listings={}),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )

    row = next(r for r in plan.rows if r.path == "p")
    assert row.with_resolved["retry"] == {"max": 2, "sync_first": True}
    assert row.with_resolved["allow_default_branch"] is True


def test_a_planned_row_without_retry_has_none() -> None:
    plan = plan_run(
        ResolvedTree(root=template(AUTO + push()), callees=()),
        fixtures.inputs(values={}),
        git=FakeGit(refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA}, files={}, listings={}),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )

    assert "retry" not in next(r for r in plan.rows if r.path == "p").with_resolved
