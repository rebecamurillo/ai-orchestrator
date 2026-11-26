"""Structure of the initiative-package guide pages (story 4, epic 9). No prose is asserted."""

from __future__ import annotations

import re

from check_guide import parse_page

from tests.unit.conftest import REPO_ROOT

GUIDE = REPO_ROOT / "guide" / "initiatives"
SPINE = REPO_ROOT / "_bmad-output" / "architecture" / "ARCHITECTURE-SPINE.md"

HEADINGS = (
    "package.yaml",
    "Template type",
    "The conversation kind",
    "The step file and its words",
    "The gate",
    "The status map",
    "Install without a screen",
    "Reopen",
    "Upgrades",
)

AMENDMENT = (
    "- **Amendment** *(initiative orchestrator-initiative-steps, 2026-11-22, decision B12)***:** "
    "The initiative procedure of the retired initiative-spec kit skill (initiatives/spec, "
    "initiatives/chain) is carried by the project's package in its hub repository (AD-39); the "
    "guide holds a pointer page for each and the package format page initiatives/package. Every "
    "other procedure of the four retired kit skills stays in the guide."
)


def read(name: str) -> tuple[dict[str, str], str]:
    meta, body, error = parse_page((GUIDE / name).read_text())
    assert error == "" and meta is not None
    return meta, body


def test_package_page_front_matter_and_headings() -> None:
    meta, body = read("package.md")
    assert meta == {"title": "Initiative packages", "kind": "page", "audience": "any"}
    found = tuple(line[3:] for line in body.split("\n") if line.startswith("## "))
    assert found == HEADINGS


def test_pointer_pages_keep_front_matter_and_stay_short() -> None:
    expected = {
        "spec.md": {
            "title": "Initiative spec — idea → ready-to-dev",
            "kind": "procedure",
            "audience": "any",
        },
        "chain.md": {"title": "The chain, step by step", "kind": "page", "audience": "any"},
    }
    for name, front in expected.items():
        meta, body = read(name)
        assert meta == front
        assert len(body.strip("\n").split("\n")) <= 10
        assert "initiatives/package" in body


def test_run_page_names_the_package() -> None:
    text = (GUIDE / "run.md").read_text()
    assert "initiatives/spec" not in text
    assert "initiatives/package" in text


def test_spine_ad32_ends_with_the_amendment() -> None:
    text = SPINE.read_text()
    match = re.search(r"^### AD-32.*?(?=^### )", text, re.S | re.M)
    assert match is not None
    assert match.group(0).rstrip().endswith(AMENDMENT)
