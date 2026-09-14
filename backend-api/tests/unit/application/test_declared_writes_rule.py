"""`rules/protected_paths.declared`: reading a row's declared writes, and nothing more.

The rule is pure and this module gives it no ports at all — the same shape
`test_protected_paths_rule.py` uses for `build`, `uncommitted` and `check`. What is settled
here is only the reading: which row values count as a declaration, and what a row written
before the key existed answers.

`check` itself is unchanged by this: a declared path is subtracted the same way an Operator's
*Accept* is, so the subtraction is asserted through the argument `check` already had.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.rules.protected_paths import check, declared
from orchestrator.domain.ports.git import Change

AGENTS = "AGENTS.md"
SPEC = "specs/notify/SPEC.md"


def row(**with_resolved: Any) -> dict[str, Any]:
    return dict(with_resolved)


# ── what counts as a declaration ────────────────────────────────────────────


def test_the_declared_paths_are_read_off_the_row_in_order() -> None:
    assert declared(row(writes=[AGENTS, SPEC])) == (AGENTS, SPEC)


def test_a_row_with_no_key_at_all_declares_nothing() -> None:
    """Every row planned before this key existed, and every kind that is not `agent`."""
    assert declared(row()) == ()


def test_a_row_whose_key_is_empty_declares_nothing() -> None:
    assert declared(row(writes=[])) == ()


def test_a_string_is_not_a_list_of_paths_and_declares_nothing() -> None:
    """A defence, not a shape the parser can produce: it refuses a bare string up front.
    Read as one path per character it would accept anything, which is the one reading a
    rule about what may be written must never take."""
    assert declared(row(writes=AGENTS)) == ()


def test_an_entry_that_is_not_a_path_is_dropped_and_the_rest_are_kept() -> None:
    assert declared(row(writes=[AGENTS, 3])) == (AGENTS,)


# ── what `check` then does with it ──────────────────────────────────────────


def test_a_declared_agents_file_is_not_a_hit() -> None:
    changed = (Change(path=AGENTS, kind="added"),)

    assert check(changed, frozenset(), declared(row(writes=[AGENTS]))) == ()


def test_an_anchor_nobody_declared_is_still_a_hit_beside_a_declared_one() -> None:
    changed = (Change(path=AGENTS, kind="added"), Change(path=SPEC, kind="modified"))

    hits = check(changed, frozenset({SPEC}), declared(row(writes=[AGENTS])))

    assert [hit.path for hit in hits] == [SPEC]


def test_a_declaration_matching_nothing_that_changed_costs_nothing() -> None:
    changed = (Change(path=SPEC, kind="modified"),)

    hits = check(changed, frozenset({SPEC}), declared(row(writes=[AGENTS])))

    assert [hit.path for hit in hits] == [SPEC]


def test_a_declaration_is_the_exact_path_and_never_a_prefix() -> None:
    """`web-client/AGENTS.md` is a different file from the root one, and AD-17 protects
    every one of them: declaring the root file does not license a child."""
    changed = (Change(path="web-client/AGENTS.md", kind="added"),)

    hits = check(changed, frozenset(), declared(row(writes=[AGENTS])))

    assert [hit.path for hit in hits] == ["web-client/AGENTS.md"]
