"""Tests for `stall_min` — the activity-based stall detector's template key.

FR-10, operator revision 2026-09-15: agent steps gain an optional `stall_min` key that
the validator accepts (integer >= 1), rejects (0, negatives, non-integers), and refuses
on template-call steps (same CALL_TIMING rule as `timeout_min`).  The planner propagates
it into `with_resolved` from either the template or `KindMeta.stall_default_min`.
"""

from __future__ import annotations

import pytest

from orchestrator.application.steps import KIND_META
from orchestrator.application.templates.keys import check_keys
from orchestrator.application.templates.model import CALL_TIMING, INVALID_TIMEOUT
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateVersion
from tests.unit.application.templates import parsed, reasons
from tests.unit.fakes.templates import FakeTemplateVersionRepository

# ---------------------------------------------------------------------------
# Minimal YAML helpers
# ---------------------------------------------------------------------------

_HEAD = "name: story\nversion: 1\n"
_AGENT_STEP = "steps:\n  - id: build\n    uses: agent\n    gate: liveness\n"
_LEAF = "name: leaf\nversion: 1\nsteps:\n  - id: s\n    uses: git.sync\n    gate: deterministic\n"
_CALL = "steps:\n  - id: build\n    uses: template\n    with:\n      name: leaf\n      version: 1\n"


def _check(text: str) -> list[str]:
    errors, _ = check_keys(parsed(text))
    return reasons(errors)


# ---------------------------------------------------------------------------
# Validator — accepted
# ---------------------------------------------------------------------------


def test_stall_min_positive_integer_is_accepted() -> None:
    assert _check(_HEAD + _AGENT_STEP + "    stall_min: 10\n") == []


def test_stall_min_one_is_the_minimum_accepted_value() -> None:
    assert _check(_HEAD + _AGENT_STEP + "    stall_min: 1\n") == []


# ---------------------------------------------------------------------------
# Validator — rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("written", ["0", "-1", "true", "many"])
def test_stall_min_that_is_not_a_positive_integer_is_invalid(written: str) -> None:
    assert _check(_HEAD + _AGENT_STEP + f"    stall_min: {written}\n") == [INVALID_TIMEOUT]


# ---------------------------------------------------------------------------
# Validator — call timing rule
# ---------------------------------------------------------------------------


def test_stall_min_on_a_template_call_step_is_refused() -> None:
    leaf = TemplateVersion(name="leaf", version=1, yaml=_LEAF, hash="sha")
    repo = FakeTemplateVersionRepository([leaf])
    result = validate(_HEAD + _CALL + "    stall_min: 10\n", templates=repo)
    reasons_list = [e.reason for e in result.errors]
    assert CALL_TIMING in reasons_list


# ---------------------------------------------------------------------------
# KindMeta defaults (operator revision 2026-09-15)
# ---------------------------------------------------------------------------


def test_kind_meta_agent_has_stall_default_min_of_30() -> None:
    assert KIND_META["agent"].stall_default_min == 30  # noqa: PLR2004


def test_kind_meta_agent_has_no_wall_clock_timeout_by_default() -> None:
    """Operator revision 2026-09-15: timeout_default_min changed from 90 to None."""
    assert KIND_META["agent"].timeout_default_min is None


def test_non_agent_kinds_have_no_stall_default() -> None:
    """stall_min is only for agent steps; shell and git.* are unchanged."""
    for kind in ("shell", "git.worktree", "git.sync", "git.commit"):
        assert KIND_META[kind].stall_default_min is None, f"{kind} should have no stall default"


# ---------------------------------------------------------------------------
# _resolved() — stall_min from parsed Step (unit-level)
# ---------------------------------------------------------------------------


def test_validate_parses_stall_min_from_template() -> None:
    """A validated Step carries the stall_min the YAML declared."""
    text = _HEAD + _AGENT_STEP + "    stall_min: 10\n"
    repo = FakeTemplateVersionRepository([])
    result = validate(text, templates=repo)
    assert result.template is not None, result.errors
    step = result.template.steps[0]
    assert step.stall_min == 10  # type: ignore[union-attr]  # noqa: PLR2004


def test_validate_step_without_stall_min_has_none() -> None:
    """When `stall_min` is absent from the YAML, `Step.stall_min` is `None`."""
    text = _HEAD + _AGENT_STEP
    repo = FakeTemplateVersionRepository([])
    result = validate(text, templates=repo)
    assert result.template is not None, result.errors
    step = result.template.steps[0]
    assert step.stall_min is None  # type: ignore[union-attr]
