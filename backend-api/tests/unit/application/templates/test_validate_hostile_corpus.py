"""Hostile Template text never escapes `judge_text`, and the storable cases are `invalid value`
from `validate()` itself (story 4, AD-26, D13)."""

from __future__ import annotations

import pytest

from orchestrator.application.templates.validate import validate
from orchestrator.application.use_cases.template_judge import judge_text
from tests.unit.fakes.templates import FakeTemplateVersionRepository

STEP = "steps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
HEAD = "name: h\nversion: 1\n"
OK_INPUT = "inputs:\n  ok:\n    type: string\n"
INVALID_VALUE = "invalid value"
FOURTH_LINE = 4
THIRD_LINE = 3
BIG_VERSION = 3_000_000_000


def check(text: str) -> list[tuple[int, str]]:
    result = validate(text, templates=FakeTemplateVersionRepository())
    return [(e.line, e.reason) for e in result.errors]


@pytest.mark.parametrize("key", ["5", "~", "1.5", "2026-01-01"])
def test_a_non_string_input_name_is_invalid_value_at_its_own_line(key: str) -> None:
    text = f"{HEAD}{OK_INPUT}  {key}:\n    type: string\n{STEP}"

    assert (FOURTH_LINE + 2, INVALID_VALUE) in check(text)
    result = validate(text, templates=FakeTemplateVersionRepository())
    assert result.template is None


@pytest.mark.parametrize(
    ("text", "line"),
    [
        (f'{HEAD}description: "a\\0b"\n{STEP}', THIRD_LINE),
        (f'{HEAD}description: "\\ud800"\n{STEP}', THIRD_LINE),
        (f'{HEAD}"\\ud800": x\n{STEP}', THIRD_LINE),
        (
            f"{HEAD}steps:\n  - id: c\n    uses: template\n    with:\n"
            '      name: "\\ud800"\n      inputs: {}\n',
            7,
        ),
    ],
)
def test_a_string_the_store_cannot_hold_is_invalid_value(text: str, line: int) -> None:
    assert (line, INVALID_VALUE) in check(text)


def test_a_call_version_beyond_int4_is_refused() -> None:
    text = (
        f"{HEAD}steps:\n  - id: c\n    uses: template\n    with:\n"
        f"      name: lib\n      version: {BIG_VERSION}\n      inputs: {{}}\n"
    )

    assert {reason for _, reason in check(text)} & {INVALID_VALUE, "non-literal version"}


def typos() -> list[str]:
    return [
        "[" * 5000,
        "x: 2026-02-30",
        "x: !!int 0x",
        "x: !!int",
        "x: !!float",
        "x: !!bool",
        "x: !!bool maybe",
        "x: !!timestamp",
        "x: !!timestamp foo",
    ]


def non_string_names() -> list[str]:
    return [
        f"{HEAD}{OK_INPUT}  {key}:\n    type: string\n{STEP}"
        for key in ("5", "~", "1.5", "2026-01-01")
    ]


def loops(bind_key: str) -> str:
    return (
        f"{HEAD}inputs:\n  list:\n    type: path\nsteps:\n  - id: e\n"
        '    for_each: "{{list}}"\n    as: item\n'
        f"    bind:\n      {bind_key}: x\n    steps:\n"
        "      - id: s\n        uses: git.sync\n        gate: deterministic\n"
    )


def unhashable() -> list[str]:
    texts = []
    for field in ("uses", "gate"):
        for value in ("[a]", "{a: 1}"):
            texts.append(f"{HEAD}steps:\n  - id: s\n    uses: git.sync\n    {field}: {value}\n")
    for value in ("[string]", "{a: 1}"):
        texts.append(f"{HEAD}inputs:\n  i:\n    type: {value}\n{STEP}")
    for value in ("[[done]]", "{a: 1}"):
        texts.append(
            f"{HEAD}steps:\n  - id: s\n    uses: git.sync\n    gate: deterministic\n"
            f"    on_fail:\n      status_in: {value}\n"
        )
    for value in ("[build]", "{a: 1}"):
        texts.append(
            f"{HEAD}steps:\n  - id: s\n    uses: git.sync\n    gate: deterministic\n"
            f"    on_fail:\n      redispatch: {value}\n"
        )
    return texts


def storable() -> list[str]:
    return [
        f'{HEAD}description: "a\\0b"\n{STEP}',
        f'{HEAD}description: "\\ud800"\n{STEP}',
        f"{HEAD}steps:\n  - id: c\n    uses: template\n    with:\n"
        '      name: "\\ud800"\n      inputs: {}\n',
        f"{HEAD}steps:\n  - id: c\n    uses: template\n    with:\n"
        f"      name: lib\n      version: {BIG_VERSION}\n      inputs: {{}}\n",
    ]


def anchor_chain() -> str:
    lines = ["a0: &a0 [x]"] + [f"a{n}: &a{n} [*a{n - 1}]" for n in range(1, 3000)]
    return HEAD + "\n".join(lines) + "\ndescription: *a2999\n" + STEP


CORPUS = [
    *typos(),
    *non_string_names(),
    *(loops(key) for key in ("5", "~", "1.5")),
    *unhashable(),
    *storable(),
    "[" * 5000,
    anchor_chain(),
]


@pytest.mark.parametrize("text", CORPUS, ids=lambda t: f"{len(t)}:{t[:30]!r}")
def test_judge_text_never_raises(text: str) -> None:
    result = judge_text(text, FakeTemplateVersionRepository())

    assert result.errors or result.template is not None
