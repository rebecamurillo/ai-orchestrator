"""`CloneCheckLine`, the defaulted `lines`, and the one place the `hint` rule is written.

`tests/unit/test_repository_entity.py` is frozen (2.2) and knows a four-field `CloneCheck`,
so what 2.3 adds is asserted here: that the new field defaults to nothing — which is why
every construction that file makes still compiles, and why every row 2.2 wrote still reads —
and that `hint` is a pure derivation rather than a fifth stored value that could go stale.

The hint exists because "`fatal: repository not found`" is git's sentence, not an answer to
"what do I do now". Three failures have an answer, and the API and the UI both restate it,
so it is derived once here.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.domain.entities.repository import (
    AUTH_HINT,
    LINE_CLONE,
    LINE_DEFAULT_BRANCH,
    LINE_LS_REMOTE,
    LINE_METHOD_VERSION,
    NOT_FOUND_HINT,
    CloneCheck,
    CloneCheckLine,
)

AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def a_line(**overrides: object) -> CloneCheckLine:
    fields: dict[str, object] = {
        "name": LINE_LS_REMOTE,
        "status": "ok",
        "seconds": 0.5,
        "output": "reachable",
    }
    fields.update(overrides)
    return CloneCheckLine(**fields)  # type: ignore[arg-type]


def a_check(**overrides: object) -> CloneCheck:
    fields: dict[str, object] = {
        "status": "failed",
        "at": AT,
        "output": "",
        "bmad_version": None,
        "lines": (),
    }
    fields.update(overrides)
    return CloneCheck(**fields)  # type: ignore[arg-type]


# ── the line ─────────────────────────────────────────────────────────────────


def test_a_line_carries_its_name_status_duration_and_output() -> None:
    line = a_line()

    assert (line.name, line.status, line.seconds, line.output) == (
        LINE_LS_REMOTE,
        "ok",
        0.5,
        "reachable",
    )


def test_a_line_is_frozen() -> None:
    line = a_line()

    with pytest.raises(ValueError, match="frozen"):
        line.status = "failed"  # type: ignore[misc]


def test_a_line_status_is_only_ok_or_failed() -> None:
    """A line is one command that ran; `pending` is a property of the check, not of a line."""
    with pytest.raises(ValueError, match="status"):
        a_line(status="pending")


def test_the_four_line_names_are_the_ones_the_check_reports() -> None:
    """Named here so the API, the UI and the use case cannot each spell them differently."""
    assert (LINE_LS_REMOTE, LINE_CLONE, LINE_DEFAULT_BRANCH, LINE_METHOD_VERSION) == (
        "ls-remote",
        "clone",
        "default branch",
        "method version",
    )


# ── the defaulted lines ──────────────────────────────────────────────────────


def test_a_check_built_without_lines_has_none() -> None:
    """2.2's constructions state four fields; they must keep compiling and keep meaning this."""
    check = CloneCheck(status="ok", at=AT, output="", bmad_version="6.11.0")

    assert check.lines == ()


def test_the_pending_check_still_carries_no_lines() -> None:
    assert CloneCheck.pending().lines == ()


def test_lines_are_held_as_a_tuple_whatever_they_arrive_as() -> None:
    check = a_check(lines=[a_line()])

    assert isinstance(check.lines, tuple)


def test_a_check_is_still_frozen_with_lines_on_it() -> None:
    check = a_check(lines=(a_line(),))

    with pytest.raises(ValueError, match="frozen"):
        check.lines = ()  # type: ignore[misc]


# ── the hint ─────────────────────────────────────────────────────────────────


def test_a_check_that_did_not_fail_offers_no_hint() -> None:
    assert a_check(status="ok").hint == ""


def test_a_pending_check_offers_no_hint() -> None:
    assert CloneCheck.pending().hint == ""


@pytest.mark.parametrize(
    "output",
    [
        "remote: Repository not found.",
        "fatal: Repository not found for 'https://x/y.git'",
        # what the local and `file://` transports say instead, for the same situation
        "fatal: '/work/e2e-fixtures/x.git' does not appear to be a git repository",
    ],
)
def test_a_repository_the_remote_does_not_have_names_the_url(output: str) -> None:
    check = a_check(output=output, lines=(a_line(status="failed", output=output),))

    assert check.hint == NOT_FOUND_HINT
    assert "URL" in NOT_FOUND_HINT


@pytest.mark.parametrize(
    "output",
    [
        "fatal: Authentication failed for 'https://github.com/org/x.git/'",
        "fatal: could not read Username for 'https://github.com': terminal prompts disabled",
    ],
)
def test_a_credential_the_remote_refused_names_the_instance_token(output: str) -> None:
    check = a_check(output=output, lines=(a_line(status="failed", output=output),))

    assert check.hint == AUTH_HINT
    assert "GitHub token" in AUTH_HINT


def test_a_refused_credential_is_reported_as_one_even_beside_a_not_found_line() -> None:
    """`could not read Username` is unambiguous; `Repository not found` is what a private
    repository answers whether the token is wrong or the name is."""
    output = "remote: Repository not found.\nfatal: Authentication failed"
    check = a_check(output=output, lines=(a_line(status="failed", output=output),))

    assert check.hint == AUTH_HINT


def test_a_missing_default_branch_is_reported_as_the_line_reported_it() -> None:
    missing = "branch develop does not exist on origin"
    check = a_check(
        output=missing,
        lines=(
            a_line(),
            a_line(name=LINE_CLONE, output="cloned 4096 bytes"),
            a_line(name=LINE_DEFAULT_BRANCH, status="failed", output=missing),
        ),
    )

    assert check.hint == missing


def test_a_failure_no_rule_recognises_offers_no_hint() -> None:
    """Guessing at an unrecognised git error would be worse than saying nothing."""
    output = "fatal: the remote end hung up unexpectedly"
    check = a_check(output=output, lines=(a_line(status="failed", output=output),))

    assert check.hint == ""


def test_a_branch_line_that_failed_for_another_reason_is_not_a_missing_branch() -> None:
    """Only the rule's own words are a hint; git's other failures here are not diagnosed."""
    output = "fatal: the remote end hung up unexpectedly"
    check = a_check(
        output=output, lines=(a_line(name=LINE_DEFAULT_BRANCH, status="failed", output=output),)
    )

    assert check.hint == ""


def test_a_failed_check_with_no_failed_line_offers_no_hint() -> None:
    """Nothing writes this, but the rule must not index into an empty list to say so."""
    assert a_check(lines=(a_line(),)).hint == ""


def test_the_hint_reads_the_lines_and_not_only_the_summary_output() -> None:
    """The summary is one line's output; the rule must still fire when it is empty."""
    check = a_check(lines=(a_line(status="failed", output="remote: Repository not found."),))

    assert check.hint == NOT_FOUND_HINT
