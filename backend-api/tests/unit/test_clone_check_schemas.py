"""The two clone-check read models, and the four-key shape they were kept out of.

`tests/unit/test_repository_schemas.py` is frozen (2.2) and knows `RepositoryOut` as it was;
what this story adds to it — two siblings of `clone_check` — is asserted here, together with
the property that made them siblings rather than keys: `clone_check` still serialises to
exactly the four keys 2.2 published, for a checked Repository as much as an unchecked one.

`hint` is asserted to come out of the domain rule rather than out of the payload, because a
read model that recomputed it would be the second place the rule lived.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from orchestrator.api.schemas.clone_check import CloneCheckLineOut, CloneCheckResultOut
from orchestrator.api.schemas.projects import RepositoryOut
from orchestrator.domain.entities.repository import (
    DEFAULT_PACKAGE_MANAGER,
    LINE_CLONE,
    LINE_LS_REMOTE,
    NOT_FOUND_HINT,
    SUGGESTED_TEST_GLOBS,
    CloneCheck,
    CloneCheckLine,
    Repository,
)
from orchestrator.domain.ids import new_id

AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)

#: The keys 2.2 published, and the ones a Repository read still answers with.
CLONE_CHECK_KEYS = {"status", "at", "output", "bmad_version"}

LINES = (
    CloneCheckLine(name=LINE_LS_REMOTE, status="ok", seconds=0.5, output="reachable"),
    CloneCheckLine(
        name=LINE_CLONE, status="failed", seconds=1.5, output="remote: Repository not found."
    ),
)

TWO = 2


def a_check(**overrides: object) -> CloneCheck:
    fields: dict[str, object] = {
        "status": "failed",
        "at": AT,
        "output": "remote: Repository not found.",
        "bmad_version": None,
        "lines": LINES,
    }
    fields.update(overrides)
    return CloneCheck(**fields)  # type: ignore[arg-type]


def a_repository(clone_check: CloneCheck, project_id: UUID | None = None) -> Repository:
    return Repository(
        id=new_id(),
        project_id=project_id or new_id(),
        slug="my-repo",
        url="https://github.com/org/my-repo.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=SUGGESTED_TEST_GLOBS,
        package_manager=DEFAULT_PACKAGE_MANAGER,
        clone_check=clone_check,
        created_at=AT,
        updated_at=AT,
    )


# ── the dedicated result ─────────────────────────────────────────────────────


def test_the_result_carries_the_whole_check() -> None:
    out = CloneCheckResultOut.of(a_check())

    assert out.status == "failed"
    assert out.output == "remote: Repository not found."
    assert len(out.lines) == TWO
    assert out.bmad_version is None


def test_the_result_carries_the_hint_the_domain_rule_derives() -> None:
    assert CloneCheckResultOut.of(a_check()).hint == NOT_FOUND_HINT


def test_a_line_is_rendered_field_for_field() -> None:
    out = CloneCheckLineOut.of(LINES[0])

    assert out.model_dump() == {
        "name": LINE_LS_REMOTE,
        "status": "ok",
        "seconds": 0.5,
        "output": "reachable",
    }


def test_the_lines_keep_the_order_they_ran_in() -> None:
    out = CloneCheckResultOut.of(a_check())

    assert [line.name for line in out.lines] == [LINE_LS_REMOTE, LINE_CLONE]


def test_a_check_that_never_ran_reads_pending_with_nothing_in_it() -> None:
    out = CloneCheckResultOut.of(CloneCheck.pending())

    assert (out.status, out.at, out.output, out.bmad_version) == ("pending", None, "", None)
    assert out.lines == []
    assert out.hint == ""


def test_the_timestamp_leaves_as_the_utc_form_the_ui_parses() -> None:
    assert CloneCheckResultOut.of(a_check()).model_dump()["at"] == "2026-09-05T12:00:00Z"


# ── the Repository read ──────────────────────────────────────────────────────


def test_a_checked_repository_still_answers_exactly_the_four_clone_check_keys() -> None:
    """The reason the lines are siblings: this dict is compared verbatim by a frozen test."""
    body = RepositoryOut.of(a_repository(a_check())).model_dump()

    assert set(body["clone_check"]) == CLONE_CHECK_KEYS


def test_an_unchecked_repository_answers_the_same_four_keys() -> None:
    body = RepositoryOut.of(a_repository(CloneCheck.pending())).model_dump()

    assert set(body["clone_check"]) == CLONE_CHECK_KEYS


def test_the_lines_are_published_beside_the_check_not_inside_it() -> None:
    body = RepositoryOut.of(a_repository(a_check())).model_dump()

    assert [line["name"] for line in body["clone_check_lines"]] == [LINE_LS_REMOTE, LINE_CLONE]


def test_the_hint_is_published_beside_the_check_too() -> None:
    body = RepositoryOut.of(a_repository(a_check())).model_dump()

    assert body["clone_check_hint"] == NOT_FOUND_HINT


def test_an_unchecked_repository_publishes_no_lines_and_no_hint() -> None:
    body = RepositoryOut.of(a_repository(CloneCheck.pending())).model_dump()

    assert body["clone_check_lines"] == []
    assert body["clone_check_hint"] == ""
