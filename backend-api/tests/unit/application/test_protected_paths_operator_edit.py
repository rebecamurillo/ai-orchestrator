"""AD-17's proof that an operator's `spec_edit` commit, made between two attempts of the
same Story frame, is invisible to the next attempt's protected-path check (story 6-3).

`FrameAnchors.check` (`application/rules/protected_paths.py`) only diffs `self.ranges` —
one `(start_sha, end_sha)` per attempt the frame recorded — so a commit made between two
attempts (after one `end_sha`, before the next `start_sha`) is never a range endpoint, and
is therefore never asked about at all. That is a fact about which `Git.diff_changes` calls
`check` makes, not about what any one of them answers, so this test scripts `FakeGit` to
answer *only* for the one recorded range and then proves, over the call log itself, that the
operator's own commit sha never appears as either end of any call `check` made — "unit test
over the fakes with the SHAs" (AC4's own words).
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.rules.protected_paths import FrameAnchors
from orchestrator.domain.ports.git import Change
from tests.unit.fakes.git import FakeGit

ANCHOR = "specs/gates/SPEC.md"
WORKTREE = Path("/work/acme/widgets/wt/gates")

#: The one attempt this frame recorded a range for.
ATTEMPT_START = "aaaa000000000000000000000000000000aaaa"
ATTEMPT_END = "bbbb000000000000000000000000000000bbbb"
#: The operator's own `spec_edit` commit, landed on the branch strictly after `ATTEMPT_END`
#: — between the two attempts, exactly where AD-17's own docstring says one lands.
OPERATOR_SHA = "cccc000000000000000000000000000000cccc"


def test_the_operator_commit_never_appears_as_a_range_endpoint() -> None:
    git = FakeGit(diff_changes=[()])
    anchors = FrameAnchors(
        git=git,
        worktree=WORKTREE,
        anchors=frozenset({ANCHOR}),
        ranges=((ATTEMPT_START, ATTEMPT_END),),
    )

    result = anchors.check(changed=(), accepted=())

    assert result == ()
    calls = git.called("diff_changes")
    assert calls == [(WORKTREE, ATTEMPT_START, ATTEMPT_END)]
    for call in calls:
        assert OPERATOR_SHA not in call


def test_a_hit_inside_the_recorded_range_is_still_caught() -> None:
    """The contrast case: the same anchor, changed *inside* the recorded range, is exactly
    what `check` exists to catch — proving the test above is a property of the range, not of
    `FrameAnchors` never reporting anything at all."""
    git = FakeGit(diff_changes=[(Change(path=ANCHOR, kind="modified"),)])
    anchors = FrameAnchors(
        git=git,
        worktree=WORKTREE,
        anchors=frozenset({ANCHOR}),
        ranges=((ATTEMPT_START, ATTEMPT_END),),
    )

    result = anchors.check(changed=(), accepted=())

    assert result == (ANCHOR,)
