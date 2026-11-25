"""AD-36 is written into the member spine between AD-35 and AD-38 (story 1 of epic 7)."""

from __future__ import annotations

from tests.unit.conftest import REPO_ROOT

SPINE = (REPO_ROOT / "_bmad-output" / "architecture" / "ARCHITECTURE-SPINE.md").read_text()
HEADING = (
    "### AD-36 — an initiative stores facts, never a status "
    "*(ratified 2026-11-22, initiative orchestrator-initiative-steps)*"
)
AMENDMENT = (
    "- **Amendment** *(initiative orchestrator-initiative-steps, 2026-11-22, after projection"
)


def test_the_entry_appears_once_between_ad_35_and_ad_38() -> None:
    assert SPINE.count(HEADING) == 1
    assert SPINE.index("### AD-35") < SPINE.index(HEADING) < SPINE.index("### AD-38")
    assert SPINE.index("### AD-38") < SPINE.index("## Consistency Conventions")


def test_the_entry_carries_binds_prevents_rule_table_and_amendment_in_order() -> None:
    entry = SPINE[SPINE.index(HEADING) : SPINE.index("### AD-38")]

    order = [
        "- **Binds:** `domain/entities/initiative.py`",
        "- **Prevents:** a third status writer",
        "- **Rule:**",
        "| Facts | Status |",
        "| `cancelled_at` set | `cancelled` |",
        "| anything else (an advance not consumed without `blocked_reason`",
        "Islands derive nothing (hard rule 4).",
        AMENDMENT,
    ]
    positions = [entry.index(item) for item in order]
    assert positions == sorted(positions)
    assert "last_opened_at, a view mark no status reads." in entry
