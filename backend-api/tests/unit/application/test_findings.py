"""The finding-code registry (story 1, SPEC CAP-1; AD-15 amended 2026-11-11)."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType

import pytest

from orchestrator.application import findings
from orchestrator.application.findings import (
    CODE_BY_REASON,
    CODE_PATTERN,
    REGISTRY,
    TEMPLATE_UNKNOWN_KEY,
    CodeEntry,
    code_for,
    entry,
    guide_id,
)
from orchestrator.application.templates import model, plan_model

SRC = Path(findings.__file__).resolve().parents[1]
LIST_FILE_REASONS = {
    plan_model.LIST_FILE_NOT_FOUND,
    plan_model.LIST_FILE_NOT_A_LIST,
    plan_model.ENTRY_MISSING_FIELDS,
    plan_model.DUPLICATE_ENTRY_ID,
    plan_model.ID_NOT_PREFIX_FREE,
    plan_model.AMBIGUOUS_STORY_FILE,
    plan_model.ONLY_NOT_IN_LIST,
}
ALL_REASONS = model.FINDING_REASONS + plan_model.FINDING_REASONS


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def unregistered_constants(module: ModuleType, registry: Mapping[str, CodeEntry]) -> list[str]:
    """Upper-case string constants shaped like a code but missing from the registry."""
    pattern = re.compile(CODE_PATTERN)
    return [
        name
        for name, value in vars(module).items()
        if name.isupper()
        and isinstance(value, str)
        and pattern.match(value)
        and value not in registry
    ]


def referenced_names(source_root: Path, skip: str) -> set[str]:
    names: set[str] = set()
    for path in source_root.rglob("*.py"):
        if path.name == skip:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
    return names


def unreferenced_check_entries(
    registry: Mapping[str, CodeEntry],
    by_reason: Mapping[str, str],
    constant_of: Callable[[str], str],
    referenced: set[str],
) -> list[str]:
    mapped = set(by_reason.values())
    return [
        code
        for code, item in registry.items()
        if item.source == "check" and code not in mapped and constant_of(code) not in referenced
    ]


def constant_name(code: str) -> str:
    return next(name for name, value in vars(findings).items() if name.isupper() and value == code)


def test_every_code_matches_the_pattern_and_keys_equal_codes() -> None:
    assert REGISTRY
    for key, item in REGISTRY.items():
        assert re.match(CODE_PATTERN, key)
        assert item.code == key
    assert len({item.code for item in REGISTRY.values()}) == len(REGISTRY)


# Declared revision for story 1.3 (owner, 2026-11-12): the slug rule binds the reason-derived
# codes only; refusal codes are hand-named and later stories add more of them.
def test_each_code_is_area_and_slug_of_its_message() -> None:
    for code in CODE_BY_REASON.values():
        item = entry(code)
        assert item.code == f"{item.area}-{slug(item.message)}"


# Declared revision for story 1.3 (owner, 2026-11-12): no literal count; the registry is the
# reason codes plus the hand-written refusals, whatever later stories add to either.
def test_the_registry_is_the_reason_codes_plus_the_refusals() -> None:
    reason_codes = set(CODE_BY_REASON.values())
    assert len(ALL_REASONS) == len(set(ALL_REASONS)) == len(CODE_BY_REASON)
    assert len(reason_codes) == len(CODE_BY_REASON)
    for code in CODE_BY_REASON.values():
        assert code in REGISTRY
    others = {code for code in REGISTRY if code not in reason_codes}
    assert others == set(findings.REFUSALS)
    assert set(REGISTRY) == reason_codes | others
    assert len(REGISTRY) == len(CODE_BY_REASON) + len(findings.REFUSALS)


def test_entry_and_guide_id() -> None:
    with pytest.raises(KeyError):
        entry("template-nope")
    assert entry(TEMPLATE_UNKNOWN_KEY).message == model.UNKNOWN_KEY
    assert guide_id(TEMPLATE_UNKNOWN_KEY) == "errors/template-unknown-key"
    with pytest.raises(KeyError):
        guide_id("template-nope")


def test_code_for_an_unknown_reason_is_none() -> None:
    assert code_for("no such reason") is None
    assert code_for(model.UNKNOWN_KEY) == TEMPLATE_UNKNOWN_KEY


def test_every_code_constant_is_registered() -> None:
    assert unregistered_constants(findings, REGISTRY) == []


def test_a_planted_unregistered_constant_is_caught() -> None:
    planted = ModuleType("planted")
    planted.TEMPLATE_EXTRA = "template-extra"  # type: ignore[attr-defined]
    planted.NOT_A_CODE = "plain"  # type: ignore[attr-defined]
    assert unregistered_constants(planted, REGISTRY) == ["TEMPLATE_EXTRA"]


def test_every_reason_is_mapped_and_every_value_registered() -> None:
    for reason in ALL_REASONS:
        assert reason in CODE_BY_REASON
    for code in CODE_BY_REASON.values():
        assert code in REGISTRY


def test_areas_split_the_list_file_reasons_from_the_rest() -> None:
    for reason in ALL_REASONS:
        expected = "spec" if reason in LIST_FILE_REASONS else "template"
        assert entry(CODE_BY_REASON[reason]).area == expected


def test_message_is_the_reason_text_and_explanation_is_present() -> None:
    for reason, code in CODE_BY_REASON.items():
        item = entry(code)
        assert item.message == reason
        assert item.source == "check"
        assert item.explanation.strip()


def test_every_check_code_is_mapped_or_referenced() -> None:
    referenced = referenced_names(SRC, "findings.py")
    assert unreferenced_check_entries(REGISTRY, CODE_BY_REASON, constant_name, referenced) == []


# Declared revision for story 1.3, Operator ruling park 4 (2026-11-12): the constant map covers
# every code of REGISTRY (reason-derived and refusal entries alike), so a registry that grows
# does not change what this test pins: exactly the planted code is reported.
def test_a_planted_unreferenced_check_entry_is_caught() -> None:
    planted = CodeEntry("template-planted", "template", "planted", "x", "check")
    registry = {**REGISTRY, planted.code: planted}
    constants = {code: "REFERENCED_ELSEWHERE" for code in REGISTRY}
    constants[planted.code] = "TEMPLATE_PLANTED"
    referenced = referenced_names(SRC, "findings.py") | {"REFERENCED_ELSEWHERE"}

    found = unreferenced_check_entries(registry, {}, constants.__getitem__, referenced)

    assert found == ["template-planted"]


def test_a_name_in_a_comment_or_string_is_not_a_reference(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(
        '# TEMPLATE_A\nX = "TEMPLATE_B"\nfindings.TEMPLATE_C\nTEMPLATE_D\n'
    )
    assert referenced_names(tmp_path, "skipped.py") >= {"TEMPLATE_C", "TEMPLATE_D"}
    assert not {"TEMPLATE_A", "TEMPLATE_B"} & referenced_names(tmp_path, "skipped.py")


def test_a_skipped_file_does_not_count(tmp_path: Path) -> None:
    (tmp_path / "findings.py").write_text("TEMPLATE_E\n")
    assert "TEMPLATE_E" not in referenced_names(tmp_path, "findings.py")
