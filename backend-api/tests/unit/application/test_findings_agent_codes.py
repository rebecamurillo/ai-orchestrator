"""An agent-reported code is in the registry and named by a guide page (AD-32, story 6).

Hard rule 6: structure only; no guide prose is asserted.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from orchestrator.application.findings import REGISTRY, CodeEntry, entry, guide_id
from tests.unit.conftest import REPO_ROOT


def unnamed_agent_entries(registry: Mapping[str, CodeEntry], guide_root: Path) -> list[str]:
    text = "\n".join(p.read_text() for p in guide_root.rglob("*.md"))
    return sorted(c for c, e in registry.items() if e.source == "agent" and c not in text)


def _planted() -> Mapping[str, CodeEntry]:
    code = "refusal-agent-planted"
    return {code: CodeEntry(code, "refusal", "m", "e", "agent")}


def test_the_local_only_refusal_is_an_agent_code() -> None:
    e = entry("refusal-local-only")

    assert e.area == "refusal"
    assert e.source == "agent"
    assert e.message == "this is done on the host only"
    assert e.code == "refusal-local-only"
    assert guide_id("refusal-local-only") == "errors/refusal-local-only"


def test_every_agent_code_of_the_real_registry_is_named_by_a_page() -> None:
    assert unnamed_agent_entries(REGISTRY, REPO_ROOT / "guide") == []


def test_an_agent_code_no_page_names_is_reported(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("nothing here\n")

    assert unnamed_agent_entries(_planted(), tmp_path) == ["refusal-agent-planted"]

    (tmp_path / "b.md").write_text("report `refusal-agent-planted`\n")

    assert unnamed_agent_entries(_planted(), tmp_path) == []


def test_a_check_code_no_page_names_is_not_reported(tmp_path: Path) -> None:
    code = "refusal-check-planted"
    registry = {code: CodeEntry(code, "refusal", "m", "e", "check")}

    assert unnamed_agent_entries(registry, tmp_path) == []
