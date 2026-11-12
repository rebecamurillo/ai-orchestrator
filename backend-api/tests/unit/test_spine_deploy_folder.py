"""AD-27 to AD-31 and the AD-16 and AD-20 amendments are written into the member spine
(initiative orchestrator-deploy-folder, epic 3 story 5)."""

from __future__ import annotations

import re

import pytest

from tests.unit.conftest import REPO_ROOT

SPINE = (REPO_ROOT / "_bmad-output" / "architecture" / "ARCHITECTURE-SPINE.md").read_text()
MARKER = "ratified 2026-11-11, initiative orchestrator-deploy-folder"
TITLES = {
    "AD-27": (
        "The deploy folder is split by a shipped manifest; an upgrade writes only what "
        "the manifest names"
    ),
    "AD-28": (
        "Scripts run in a one-shot setup container that sees the harness asset folders "
        "and nothing else"
    ),
    "AD-29": (
        "One catalog per harness; every reader names the harness; failures show where "
        "the owner looks"
    ),
    "AD-30": (
        "An upgrade or an on-demand setup runs under an instance hold that no working "
        "step stands against"
    ),
    "AD-31": "Deployment tests are their own quality gate, separate from the development gates",
}


def _section(ad: str) -> str:
    start = SPINE.index(f"### {ad} — ")
    match = re.search(r"^(### |## )", SPINE[start + 4 :], re.M)
    return SPINE[start : start + 4 + match.start()] if match else SPINE[start:]


@pytest.mark.parametrize("ad", sorted(TITLES))
def test_each_new_entry_appears_once_with_the_marker(ad: str) -> None:
    heading = f"### {ad} — {TITLES[ad]}"

    assert SPINE.count(heading) == 1
    line = next(entry for entry in SPINE.splitlines() if entry.startswith(heading))
    assert MARKER in line
    body = _section(ad)
    for label in ("**Binds:**", "**Prevents:**", "**Rule:**"):
        assert body.count(label) == 1


def test_the_new_entries_follow_ad_26_in_order_before_the_conventions() -> None:
    positions = [SPINE.index("### AD-26 — ")]
    positions += [SPINE.index(f"### {ad} — ") for ad in sorted(TITLES)]
    positions.append(SPINE.index("## Consistency Conventions"))

    assert positions == sorted(positions)


@pytest.mark.parametrize(
    ("ad", "sentence"),
    [
        ("AD-16", "BMAD reaches the harnesses only through `bmad/install.sh`"),
        ("AD-20", "have their values in `release.env`, a product file"),
    ],
)
def test_ad_16_and_ad_20_carry_the_amendment(ad: str, sentence: str) -> None:
    body = _section(ad)

    assert body.count("**Amendment**") == 1
    assert MARKER in body
    assert sentence in body


def test_ad_26_is_untouched() -> None:
    assert "Amendment" not in _section("AD-26")
