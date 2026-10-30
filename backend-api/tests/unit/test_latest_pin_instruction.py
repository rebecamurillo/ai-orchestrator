"""Agents setting up `.env` files are told to pin the latest release (Operator, 2026-10-30).

The rule has to be readable wherever an agent meets the pins: the admin skill, its runbook, and
the two contract files. It also has to carry what makes it safe to follow: a pin is an exact
number, because `ensure` refuses the word `latest`, and `BMAD_VERSION` is outside the rule,
because AD-16 ties it to the manifest in every target repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

ADMIN_SKILL = REPO_ROOT / "deploy" / "kit" / "skills" / "orchestrator-admin"

#: The npm package behind each pin the rule covers, named so an agent can look it up.
PACKAGES = (
    "@anthropic-ai/claude-code",
    "@openai/codex",
    "opencode-ai",
    "@langfuse/opencode-observability-plugin",
)

READERS = (
    ADMIN_SKILL / "SKILL.md",
    ADMIN_SKILL / "references" / "runbooks.md",
    REPO_ROOT / ".env.example",
    REPO_ROOT / "deploy" / ".env.example",
)


@pytest.mark.parametrize("path", READERS, ids=lambda path: str(path.relative_to(REPO_ROOT)))
def test_every_place_an_agent_meets_the_pins_states_the_rule(path: Path) -> None:
    text = path.read_text()

    assert "npm view" in text, "says how to find the latest release"
    assert "never the word `latest`" in text, "a pin is an exact number"
    assert "BMAD_VERSION" in text, "names the pin outside the rule"
    for package in PACKAGES:
        assert package in text, package


def test_the_runbook_says_what_to_do_when_the_latest_release_does_not_work() -> None:
    text = (ADMIN_SKILL / "references" / "runbooks.md").read_text()

    assert "readiness" in text
    assert "do not fall back silently" in text
