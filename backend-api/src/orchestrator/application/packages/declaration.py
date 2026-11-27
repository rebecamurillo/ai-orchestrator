"""`package.yaml`: parse it, check every rule of AD-39, and read a template's steps.

Pure: the use case reads the files and hands their text here. Every checker collects its
problems, so one refusal names every file and reason at once.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

import yaml

from orchestrator.application.templates.model import ParsedTemplate, Step, all_steps
from orchestrator.domain.entities.project_package import ShownAs, StepDecl
from orchestrator.domain.entities.repository import is_valid_folder

PACKAGE_FILE = "package.yaml"
PACKAGE_KEYS = ("name", "sequence", "gate", "status_map")
NAME_PATTERN = re.compile(r"[a-z][a-z0-9-]*")
OWNERS_KEY_PATTERN = re.compile(r"[a-z_][a-z0-9_]*")
STATUS_WORDS = ("done", "running", "waiting for her", "failed")
SPEC_GATE_ROLE = "spec-gate"
TEMPLATE_SUFFIX = ".yaml"
GATE_KEYS = ("pass", "fail", "owners_key")
ENTRY_KEYS = ("workflow", "template")


@dataclass(frozen=True)
class PackageProblem:
    """One refusal: the file it concerns and the reason."""

    file: str
    reason: str


class PackageInvalid(Exception):
    """A package that cannot be installed, with every problem found."""

    def __init__(self, problems: Sequence[PackageProblem]) -> None:
        super().__init__("; ".join(f"{p.file}: {p.reason}" for p in problems))
        self.problems = tuple(problems)


@dataclass(frozen=True)
class ParsedEntry:
    workflow: str
    template: str
    is_file: bool


@dataclass(frozen=True)
class ParsedPackage:
    name: str
    entries: tuple[ParsedEntry, ...]
    pass_words: tuple[str, ...]
    fail_words: tuple[str, ...]
    owners_key: str
    status_map: dict[str, str]


def _is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _check_name(data: dict[str, object], file: str) -> list[PackageProblem]:
    name = data.get("name")
    if isinstance(name, str) and NAME_PATTERN.fullmatch(name):
        return []
    return [PackageProblem(file, "name: must match ^[a-z][a-z0-9-]*$")]


def _check_entry(entry: object, index: int, file: str) -> list[PackageProblem]:
    where = f"sequence[{index}]"
    if not isinstance(entry, dict):
        return [PackageProblem(file, f"{where}: must be a mapping")]
    problems = [
        PackageProblem(file, f"{where}: unknown key {key}")
        for key in entry
        if key not in ENTRY_KEYS
    ]
    workflow, template = entry.get("workflow"), entry.get("template")
    if not (isinstance(workflow, str) and NAME_PATTERN.fullmatch(workflow)):
        problems.append(PackageProblem(file, f"{where}: workflow must match ^[a-z][a-z0-9-]*$"))
    if not _is_text(template):
        problems.append(PackageProblem(file, f"{where}: template must be a non-empty string"))
    elif str(template).endswith(TEMPLATE_SUFFIX) and not is_valid_folder(str(template)):
        problems.append(
            PackageProblem(file, f"{where}: template {template} is not a path inside the package")
        )
    return problems


def _check_sequence(data: dict[str, object], file: str) -> list[PackageProblem]:
    sequence = data.get("sequence")
    if not isinstance(sequence, list) or not sequence:
        return [PackageProblem(file, "sequence: must be a non-empty list")]
    problems = [p for i, entry in enumerate(sequence) for p in _check_entry(entry, i, file)]
    workflows = [
        e["workflow"]
        for e in sequence
        if isinstance(e, dict) and isinstance(e.get("workflow"), str)
    ]
    problems.extend(
        PackageProblem(file, f"workflow {w} appears twice")
        for w in dict.fromkeys(w for w in workflows if workflows.count(w) > 1)
    )
    return problems


def _words(gate: dict[str, object], key: str, file: str) -> list[PackageProblem]:
    value = gate.get(key)
    if isinstance(value, list) and value and all(_is_text(word) for word in value):
        return []
    return [PackageProblem(file, f"gate.{key}: must be a non-empty list of non-empty strings")]


def _check_gate(data: dict[str, object], file: str) -> list[PackageProblem]:
    gate = data.get("gate")
    if not isinstance(gate, dict):
        return [PackageProblem(file, "gate: must be a mapping of pass, fail and owners_key")]
    problems = [PackageProblem(file, f"gate: unknown key {k}") for k in gate if k not in GATE_KEYS]
    problems += [PackageProblem(file, f"gate: missing key {k}") for k in GATE_KEYS if k not in gate]
    problems += _words(gate, "pass", file) + _words(gate, "fail", file)
    if not problems:
        both = [w for w in gate["pass"] if w in gate["fail"]]
        problems += [
            PackageProblem(file, f"word {w} is in both gate.pass and gate.fail") for w in both
        ]
    owners = gate.get("owners_key")
    if "owners_key" in gate and not (
        isinstance(owners, str) and OWNERS_KEY_PATTERN.fullmatch(owners)
    ):
        problems.append(PackageProblem(file, "gate.owners_key: must match ^[a-z_][a-z0-9_]*$"))
    return problems


def _check_status_map(data: dict[str, object], file: str) -> list[PackageProblem]:
    status_map = data.get("status_map")
    if not isinstance(status_map, dict) or not status_map:
        return [PackageProblem(file, "status_map: must be a non-empty mapping")]
    allowed = ", ".join(STATUS_WORDS)
    problems = []
    for key, value in status_map.items():
        if not _is_text(key):
            problems.append(PackageProblem(file, f"status_map {key}: key must be a word"))
        elif value not in STATUS_WORDS:
            problems.append(
                PackageProblem(file, f"status_map {key}: {value} is not one of {allowed}")
            )
    return problems


CHECKS = (
    ("name", _check_name),
    ("sequence", _check_sequence),
    ("gate", _check_gate),
    ("status_map", _check_status_map),
)


def parse_package(text: str, file: str) -> ParsedPackage:
    """Every rule of `package.yaml`; raises `PackageInvalid` with all problems found."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        raise PackageInvalid([PackageProblem(file, "invalid yaml")]) from None
    if not isinstance(data, dict):
        raise PackageInvalid([PackageProblem(file, "invalid yaml: not a mapping")])
    problems = [PackageProblem(file, f"unknown key {k}") for k in data if k not in PACKAGE_KEYS]
    problems += [PackageProblem(file, f"missing key {k}") for k in PACKAGE_KEYS if k not in data]
    for key, check in CHECKS:
        if key in data:
            problems += check(data, file)
    if problems:
        raise PackageInvalid(problems)
    gate = data["gate"]
    return ParsedPackage(
        name=data["name"],
        entries=tuple(
            ParsedEntry(e["workflow"], e["template"], e["template"].endswith(TEMPLATE_SUFFIX))
            for e in data["sequence"]
        ),
        pass_words=tuple(gate["pass"]),
        fail_words=tuple(gate["fail"]),
        owners_key=gate["owners_key"],
        status_map=dict(data["status_map"]),
    )


def stem_of(template_path: str) -> str:
    """The file name of a package template without its `.yaml`."""
    return template_path.rsplit("/", 1)[-1].removesuffix(TEMPLATE_SUFFIX)


def duplicate_stems(entries: Sequence[ParsedEntry], path: str) -> list[PackageProblem]:
    """One problem per package template whose stem an earlier one already took."""
    seen: dict[str, str] = {}
    problems = []
    for entry in entries:
        if not entry.is_file:
            continue
        stem = stem_of(entry.template)
        if stem in seen:
            problems.append(
                PackageProblem(
                    f"{path}/{entry.template}",
                    f"two templates have the stem {stem}: {seen[stem]}, {entry.template}",
                )
            )
        else:
            seen[stem] = entry.template
    return problems


def _spec_gate_steps(parsed: ParsedTemplate) -> list[Step]:
    return [step for step in all_steps(parsed.steps) if step.role == SPEC_GATE_ROLE]


def gate_problems(
    own: Sequence[tuple[str, ParsedTemplate]], pkg: ParsedPackage, path: str
) -> list[PackageProblem]:
    """The package's own templates hold one `spec-gate` row, listing every gate word."""
    rows = [(file, step) for file, parsed in own for step in _spec_gate_steps(parsed)]
    package_file = f"{path}/{PACKAGE_FILE}"
    if not rows:
        return [PackageProblem(package_file, "no spec-gate row in the package's templates")]
    if len(rows) > 1:
        ids = ", ".join(f"{file}:{step.id}" for file, step in rows)
        return [PackageProblem(package_file, f"more than one spec-gate row: {ids}")]
    file, step = rows[0]
    listed = step.agent.expect_success if step.agent is not None else ()
    return [
        PackageProblem(
            file, f"spec-gate row {step.id} does not list gate word {word} in expect.success"
        )
        for word in (*pkg.pass_words, *pkg.fail_words)
        if word not in listed
    ]


def entry_steps(parsed: ParsedTemplate) -> tuple[StepDecl, ...]:
    """The conversation rows and the spec-gate row, in row order."""
    decls: list[StepDecl] = []
    for step in all_steps(parsed.steps):
        if step.conversation is not None:
            params = dict(step.params)
            decls.append(
                StepDecl(
                    id=str(params["step"]),
                    kind="conversation",
                    skill=_text(params.get("skill")),
                    persona=_text(params.get("persona")),
                    file=step.conversation.expect_files[0]
                    if step.conversation.expect_files
                    else None,
                    writes=step.conversation.writes,
                )
            )
        elif step.role == SPEC_GATE_ROLE:
            files = step.agent.expect_files if step.agent is not None else ()
            decls.append(
                StepDecl(
                    id=step.id,
                    kind="automatic",
                    skill=None,
                    persona=None,
                    file=files[0] if files else None,
                    writes=(),
                )
            )
    return tuple(decls)


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def shown_as(index: int, template_type: str, steps: Sequence[StepDecl]) -> ShownAs:
    """`step` for a non-first interactive entry that holds no conversation row."""
    holds_conversation = any(step.kind == "conversation" for step in steps)
    if index > 0 and template_type == "interactive" and not holds_conversation:
        return "step"
    return "workflow"
