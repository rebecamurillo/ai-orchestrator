"""AD-40 is written into the member spine after AD-35 (story 1)."""

from __future__ import annotations

from tests.unit.conftest import REPO_ROOT

SPINE = (REPO_ROOT / "_bmad-output" / "architecture" / "ARCHITECTURE-SPINE.md").read_text()
HEADING = (
    "### AD-40 — Every step that ran has a log, and one key joins its views "
    "*(ratified 2026-11-22, initiative orchestrator-initiative-steps)*"
)
FIRST = "a new `StepLog` port and its adapter"
RULE = "**The order.**"


def test_the_entry_appears_once_between_ad_35_and_the_conventions() -> None:
    assert SPINE.count(HEADING) == 1
    assert SPINE.count(FIRST) == 1
    assert SPINE.count(RULE) == 1
    assert (
        SPINE.index("### AD-35") < SPINE.index(HEADING) < SPINE.index("## Consistency Conventions")
    )
