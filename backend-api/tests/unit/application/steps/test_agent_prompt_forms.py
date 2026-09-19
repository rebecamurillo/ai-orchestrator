"""`compose_prompt` — the `prompt` and `prompt_file_content` dispatch bases.

Tests the two new dispatch forms added in story 4-3, side-by-side with the existing
`prompt_extra` and HALT behaviours to confirm neither branch breaks them.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.steps.agent_prompt import compose_prompt
from tests.unit.application.steps.agent_fixtures import resolved

CUSTOM_PROMPT = "Do X and report results."
FILE_CONTENT = "Implement the story in plan.md."


def _resolved_with_prompt(**over: Any) -> dict[str, Any]:
    """A `with_resolved` that uses the `prompt` dispatch form instead of `skill`."""
    row = resolved(**over)
    del row["skill"]
    row["prompt"] = CUSTOM_PROMPT
    return row


def _resolved_with_prompt_file(**over: Any) -> dict[str, Any]:
    """A `with_resolved` that uses the `prompt_file` dispatch form instead of `skill`."""
    row = resolved(**over)
    del row["skill"]
    row["prompt_file"] = "plan.md"
    return row


def _prompt(with_resolved: dict[str, Any], **over: Any) -> str:
    return compose_prompt(
        with_resolved,
        over.get("resume_signal"),
        over.get("previous_attempt"),
        prompt_file_content=over.get("prompt_file_content"),
    )


# --- `prompt` base ---------------------------------------------------------------------------


def test_prompt_form_returns_the_literal_value_as_base() -> None:
    assert _prompt(_resolved_with_prompt()).startswith(CUSTOM_PROMPT)


def test_prompt_form_does_not_contain_the_dispatch_sentence() -> None:
    result = _prompt(_resolved_with_prompt())

    assert "Run the skill" not in result


def test_prompt_extra_is_appended_after_prompt_base() -> None:
    result = _prompt(_resolved_with_prompt(prompt_extra="Extra instruction."))

    assert result == f"{CUSTOM_PROMPT} Extra instruction."


def test_prompt_base_with_no_extra_has_no_trailing_space() -> None:
    result = _prompt(_resolved_with_prompt(prompt_extra=""))

    assert result == CUSTOM_PROMPT


def test_halt_is_appended_to_prompt_base_when_spec_checkpoint() -> None:
    result = _prompt(_resolved_with_prompt(spec_checkpoint=True))

    assert result.endswith(" Halt after planning.")


# --- `prompt_file_content` base --------------------------------------------------------------


def test_prompt_file_content_is_used_as_base() -> None:
    result = _prompt(_resolved_with_prompt_file(), prompt_file_content=FILE_CONTENT)

    assert result.startswith(FILE_CONTENT)


def test_prompt_file_content_does_not_contain_the_dispatch_sentence() -> None:
    result = _prompt(_resolved_with_prompt_file(), prompt_file_content=FILE_CONTENT)

    assert "Run the skill" not in result


def test_prompt_extra_is_appended_after_prompt_file_content_base() -> None:
    row = _resolved_with_prompt_file(prompt_extra="Extra instruction.")
    result = _prompt(row, prompt_file_content=FILE_CONTENT)

    assert result == f"{FILE_CONTENT} Extra instruction."


def test_halt_is_appended_to_prompt_file_content_base_when_spec_checkpoint() -> None:
    row = _resolved_with_prompt_file(spec_checkpoint=True)
    result = _prompt(row, prompt_file_content=FILE_CONTENT)

    assert result.endswith(" Halt after planning.")


def test_prompt_file_content_of_empty_string_uses_empty_base() -> None:
    """_planned() passes `or ""` for a missing file; compose_prompt sees `""`, not None."""
    row = _resolved_with_prompt_file()
    result = _prompt(row, prompt_file_content="")

    # "" is not None → prompt_file_content branch fires → base is ""
    # No DISPATCH sentence, no HALT (spec_checkpoint is False)
    assert "Run the skill" not in result
