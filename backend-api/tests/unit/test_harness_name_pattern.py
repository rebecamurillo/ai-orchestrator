"""`HARNESS_NAME_PATTERN` (`domain/entities/harness.py`): the shape a harness name has.

A harness name reaches Postgres as a text comparison — `attempt.harness = :harness` under
`GET /steps`, `harness.name = :name` under `GET /harnesses/{name}/readiness` — and a
PostgreSQL text field cannot hold a NUL byte. A request carrying one therefore reached
psycopg as a `DataError` and left a 500 (`schemathesis`, 2026-09-18) for a value that could
have matched no stored row: every name this instance can hold is a lowercase slug. The
shape is declared on the parameters themselves, so such a value is refused at the edge with
a 422 naming the parameter rather than reaching the database at all.

`HARNESS_NAMES` is not that check. The `fake` harness `ORCH_TEST_MODE` seeds is a real row
with a real name and is deliberately outside that tuple
(`tests/unit/test_fake_harness_registry.py`), so filtering and reading by name stay open to
any well-shaped name; what is refused is a value no name can be.

This module pins the shape itself. The two endpoints that declare it are pinned by
`tests/unit/test_history_router_harness_shape.py` and
`tests/unit/test_harness_readiness_router_name_shape.py`.
"""

from __future__ import annotations

import re

import pytest

from orchestrator.domain.entities.harness import HARNESS_NAME_PATTERN, HARNESS_NAMES
from orchestrator.infrastructure.harness.fake.adapter import NAME as FAKE_HARNESS_NAME


def matches(value: str) -> bool:
    return re.fullmatch(HARNESS_NAME_PATTERN, value) is not None


@pytest.mark.parametrize("name", [*HARNESS_NAMES, FAKE_HARNESS_NAME])
def test_every_name_this_instance_can_hold_matches_the_shape(name: str) -> None:
    assert matches(name)


@pytest.mark.parametrize(
    "value",
    [
        "\x00",  # the value schemathesis sent, and the one Postgres cannot compare
        "\x00abc",
        "claude\x00",
        "",  # a name is at least one character
        "Claude",  # stored names are lowercase
        "claude codex",
        "../etc/passwd",
        "a" * 33,  # longer than any name this system installs
    ],
)
def test_a_value_no_harness_name_can_be_does_not_match(value: str) -> None:
    assert not matches(value)


def test_the_shape_is_anchored_at_both_ends() -> None:
    r"""Declared on a FastAPI parameter the pattern is matched unanchored, so the anchors are
    what keep `\x00claude\x00` out; a pattern without them would admit every value above."""
    assert HARNESS_NAME_PATTERN.startswith("^")
    assert HARNESS_NAME_PATTERN.endswith("$")
