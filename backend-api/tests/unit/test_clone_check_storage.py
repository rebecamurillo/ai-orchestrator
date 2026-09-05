"""How a finished check is stored, and why it is not a column of its own.

`tests/unit/test_repository_repository_adapter.py` is frozen (2.2) and asserts two things
this story may not break: that the `repository` table carries exactly thirteen columns, and
that a check with no lines serialises to exactly four keys. Both hold, because the lines live
*inside* the same `jsonb` value under a key that is written only when there are any — which
also means every row stored before this story reads back without a migration.

That last property is the one worth a test rather than a comment: a reader that indexed
`data["lines"]` would turn every Repository registered by 2.2 into a `KeyError` on the first
`GET`, and no amount of new-row testing would have found it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from orchestrator.domain.entities.repository import (
    LINE_CLONE,
    LINE_LS_REMOTE,
    CloneCheck,
    CloneCheckLine,
)
from orchestrator.infrastructure.db.repositories.repository import (
    LINES_KEY,
    clone_check_from_entity,
    clone_check_json,
)

AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)

LINES = (
    CloneCheckLine(name=LINE_LS_REMOTE, status="ok", seconds=0.5, output="reachable"),
    CloneCheckLine(name=LINE_CLONE, status="failed", seconds=1.5, output="fatal: nope"),
)

#: A row exactly as 2.2's adapter wrote it: four keys, and no `lines` at all.
ROW_WITHOUT_LINES = {
    "status": "pending",
    "at": None,
    "output": "",
    "bmad_version": None,
}


def a_check(**overrides: object) -> CloneCheck:
    fields: dict[str, object] = {
        "status": "failed",
        "at": AT,
        "output": "fatal: nope",
        "bmad_version": "6.11.0",
        "lines": LINES,
    }
    fields.update(overrides)
    return CloneCheck(**fields)  # type: ignore[arg-type]


def test_a_check_with_no_lines_writes_no_lines_key() -> None:
    """The frozen four-key assertions are what this keeps true."""
    assert LINES_KEY not in clone_check_json(CloneCheck.pending())


def test_a_check_with_lines_writes_them_inside_the_same_value() -> None:
    stored = clone_check_json(a_check())

    assert stored[LINES_KEY] == [
        {"name": LINE_LS_REMOTE, "status": "ok", "seconds": 0.5, "output": "reachable"},
        {"name": LINE_CLONE, "status": "failed", "seconds": 1.5, "output": "fatal: nope"},
    ]


def test_a_check_round_trips_through_the_stored_shape() -> None:
    assert clone_check_from_entity(clone_check_json(a_check())) == a_check()


def test_a_row_written_before_lines_existed_still_reads() -> None:
    """No migration: the key is absent, and absent means no lines ran."""
    assert clone_check_from_entity(ROW_WITHOUT_LINES) == CloneCheck.pending()


def test_the_stored_lines_keep_their_order() -> None:
    """The order is the order the commands ran; a set or a dict would lose it."""
    read = clone_check_from_entity(clone_check_json(a_check()))

    assert [line.name for line in read.lines] == [LINE_LS_REMOTE, LINE_CLONE]


def test_a_check_read_back_derives_the_same_hint() -> None:
    """`hint` is not stored, so it has to survive the round trip by being recomputed."""
    check = a_check(output="remote: Repository not found.")

    assert clone_check_from_entity(clone_check_json(check)).hint == check.hint
