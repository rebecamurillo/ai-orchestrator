"""AD-26 is written into the member spine after AD-25 (story 4)."""

from __future__ import annotations

from tests.unit.conftest import REPO_ROOT

SPINE = (REPO_ROOT / "_bmad-output" / "architecture" / "ARCHITECTURE-SPINE.md").read_text()
HEADING = (
    "### AD-26 — Templates load from two folders through one seed path; the operator's folder wins"
)
FIRST = "`TEMPLATES_DIR` (the image's shipped set, unchanged) and `OPERATOR_TEMPLATES_DIR`"
LAST = "and the web-client renders its notice from that field alone."


def test_the_entry_appears_once_after_ad_25() -> None:
    assert SPINE.count(HEADING) == 1
    assert SPINE.count(FIRST) == 1
    assert SPINE.count(LAST) == 1
    assert (
        SPINE.index("### AD-25") < SPINE.index(HEADING) < SPINE.index("## Consistency Conventions")
    )


def test_the_entry_is_marked_ratified_in_the_initiative() -> None:
    line = next(entry for entry in SPINE.splitlines() if entry.startswith(HEADING))

    assert "ratified 2026-11-06, initiative orchestrator-client-kit" in line
