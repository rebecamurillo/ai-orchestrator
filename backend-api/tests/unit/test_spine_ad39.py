"""AD-39 is written into the member spine between AD-38 and AD-40 (story 3 of epic 6)."""

from __future__ import annotations

from tests.unit.conftest import REPO_ROOT

SPINE = (REPO_ROOT / "_bmad-output" / "architecture" / "ARCHITECTURE-SPINE.md").read_text()
HEADING = (
    "### AD-39 — a client package is a folder in the hub, installed per project by reference "
    "*(ratified 2026-11-22, initiative orchestrator-initiative-steps)*"
)
BINDS = "- **Binds:** `domain/entities/project_package.py` (new), `use_cases/packages.py` (new)"
PREVENTS = "- **Prevents:** a second copy of a persona or skill (FR-25)"
RULE = "**Two projects, one package.**"


def test_the_entry_appears_once_between_ad_38_and_ad_40() -> None:
    assert SPINE.count(HEADING) == 1
    assert SPINE.count(RULE) == 1
    assert SPINE.index("### AD-38") < SPINE.index(HEADING) < SPINE.index("### AD-40")


def test_the_entry_carries_binds_prevents_and_rule_in_order() -> None:
    entry = SPINE[SPINE.index(HEADING) : SPINE.index("### AD-40")]

    assert entry.index(BINDS) < entry.index(PREVENTS) < entry.index("- **Rule:**")
    assert "name: rebecamurillo-initiatives" in entry
    assert "**Remove** is refused while an initiative" in entry
