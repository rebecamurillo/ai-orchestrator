"""`orchestrator-analysis.yaml`: what a repository declares about its own tests and tools.

Read at the base commit, never at head, so a Run cannot change the rules it is measured by.
`coverage_report` and `test_report_path` are accepted because ARCHITECTURE §7.4 declares them
beside `coverage` and `test_report`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import yaml

DECLARATION_FILE = "orchestrator-analysis.yaml"
COMMAND_KEYS = (
    "install",
    "lint",
    "typecheck",
    "coverage",
    "coverage_report",
    "test_report",
    "test_report_path",
)
TESTS_KEYS = ("unit", "e2e")
SAST_KEYS = ("rules",)
TOP_KEYS = ("tests", "tier2", "commands", "sast", "registries")
WRONG_TYPE = "wrong type: {key}"
UNKNOWN_KEY = "unknown key: {key}"
MISSING_KEY = "missing key: {key}"
NOT_RELATIVE = "not repository-relative: {key}"
REPORT_PATHS = (("coverage", "coverage_report"), ("test_report", "test_report_path"))
UNREADABLE = "declaration unreadable: {error}"
DOCUMENT = "<document>"


@dataclass(frozen=True)
class Declaration:
    tests_unit: tuple[str, ...] = ()
    tests_e2e: tuple[str, ...] = ()
    tier2: bool = False
    commands: Mapping[str, str] = field(default_factory=dict)
    sast_rules: str | None = None
    registries: Mapping[str, str] = field(default_factory=dict)


DEFAULT_DECLARATION = Declaration()


@dataclass(frozen=True)
class ParsedDeclaration:
    declaration: Declaration
    hash: str | None
    problems: tuple[str, ...]


def _strings(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return None


def _string_map(value: Any) -> dict[str, str] | None:
    if isinstance(value, dict) and all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        return dict(value)
    return None


def _section(
    document: dict[str, Any], key: str, known: tuple[str, ...], problems: list[str]
) -> dict[str, Any]:
    """A mapping section whose unknown keys are problems; a non-mapping is a problem."""
    if key not in document:
        return {}
    value = document[key]
    if not isinstance(value, dict):
        problems.append(WRONG_TYPE.format(key=key))
        return {}
    problems.extend(UNKNOWN_KEY.format(key=f"{key}.{name}") for name in value if name not in known)
    return {name: item for name, item in value.items() if name in known}


def _repository_relative(path: str) -> bool:
    return not path.startswith("/") and ".." not in path.split("/")


def _check_report_paths(commands: dict[str, str], problems: list[str]) -> None:
    for command, path_key in REPORT_PATHS:
        if path_key in commands and not _repository_relative(commands[path_key]):
            problems.append(NOT_RELATIVE.format(key=f"commands.{path_key}"))
            del commands[path_key]
        if command in commands and path_key not in commands:
            problems.append(MISSING_KEY.format(key=f"commands.{path_key}"))


def _from_document(document: dict[str, Any], problems: list[str]) -> Declaration:
    problems.extend(UNKNOWN_KEY.format(key=name) for name in document if name not in TOP_KEYS)
    tests = _section(document, "tests", TESTS_KEYS, problems)
    lists: dict[str, tuple[str, ...]] = {}
    for key in TESTS_KEYS:
        if key in tests:
            parsed = _strings(tests[key])
            if parsed is None:
                problems.append(WRONG_TYPE.format(key=f"tests.{key}"))
            else:
                lists[key] = parsed
    commands: dict[str, str] = {}
    for key, value in _section(document, "commands", COMMAND_KEYS, problems).items():
        if isinstance(value, str):
            commands[key] = value
        else:
            problems.append(WRONG_TYPE.format(key=f"commands.{key}"))
    _check_report_paths(commands, problems)
    sast = _section(document, "sast", SAST_KEYS, problems)
    rules = sast.get("rules")
    if "rules" in sast and not isinstance(rules, str):
        problems.append(WRONG_TYPE.format(key="sast.rules"))
        rules = None
    tier2 = document.get("tier2", False)
    if not isinstance(tier2, bool):
        problems.append(WRONG_TYPE.format(key="tier2"))
        tier2 = False
    registries = _string_map(document.get("registries", {}))
    if registries is None:
        problems.append(WRONG_TYPE.format(key="registries"))
        registries = {}
    return Declaration(
        tests_unit=lists.get("unit", ()),
        tests_e2e=lists.get("e2e", ()),
        tier2=tier2,
        commands=commands,
        sast_rules=rules,
        registries=registries,
    )


def parse_declaration(text: str | None) -> ParsedDeclaration:
    """`None` is an absent file: the defaults and no hash."""
    if text is None:
        return ParsedDeclaration(DEFAULT_DECLARATION, None, ())
    digest = hashlib.sha256(text.encode()).hexdigest()
    try:
        document = yaml.safe_load(text)
    except (yaml.YAMLError, RecursionError) as error:  # deep nesting overflows the parser
        problem = UNREADABLE.format(error=" ".join(str(error).split()))
        return ParsedDeclaration(DEFAULT_DECLARATION, digest, (problem,))
    if document is None:
        return ParsedDeclaration(DEFAULT_DECLARATION, digest, ())
    if not isinstance(document, dict):
        return ParsedDeclaration(DEFAULT_DECLARATION, digest, (WRONG_TYPE.format(key=DOCUMENT),))
    problems: list[str] = []
    declaration = _from_document(document, problems)
    return ParsedDeclaration(declaration, digest, tuple(problems))
