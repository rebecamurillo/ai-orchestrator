"""Two more reads of a Run's own branch, for the facts UJ-3 asserts (6.8, SPEC CAP-8).

`GatesFixture` answers "what does this path hold at this ref" and "what paths are at this
ref", which covers every earlier Epic 6 scenario. Scenario C needs two things neither can
say, and both are facts on the branch rather than rows in a database:

- **the subject of a commit.** `signal_effects.py::SKIP_MESSAGE` rewrites a skipped Story's
  commit-guard message to `story {id}: skipped by operator`, and the only place that message
  becomes observable is the commit the guard then makes.
- **which commit a message names.** The redispatch's Story file — `status: in-progress` with
  `## Verify Failure` under it (FR-10) — exists only in the prepare commit
  `application/steps/agent.py::PREPARE_MESSAGE` wrote, because the `fake` harness overwrites
  the file immediately afterwards. Finding that commit by its message and reading the file at
  it is how the assertion reaches what the redispatch actually saw.

A subclass rather than an edit: `gates_fixture.py` is shared by five modules that need none
of this, and `_either` — the "run it here, else in the container, else fail naming both" —
is exactly the routing these two reads need too.
"""

from __future__ import annotations

from tests.e2e.helpers.gates_fixture import GatesFixture

#: The subject line of one commit: `$1` worktree, `$2` ref.
SUBJECT_AT_REF = """
set -e
git -C "$1" log -1 --format=%s "$2"
"""

#: The newest commit whose subject holds `$3`, as a sha: `$1` worktree, `$2` ref.
#: `--fixed-strings`, because a commit message is prose and not a pattern.
COMMIT_MATCHING = """
set -e
git -C "$1" log --format=%H --fixed-strings --grep="$3" -1 "$2"
"""


class Uj3Reads(GatesFixture):
    """`GatesFixture` plus the two commit-level reads scenario C asserts on."""

    def subject(self, worktree: str, ref: str) -> str:
        """The subject line of the commit at `ref`, stripped."""
        arguments = [worktree, ref]
        what = f"read the subject of {ref}"
        return self._either(SUBJECT_AT_REF, arguments, arguments, what).strip()

    def commit_matching(self, worktree: str, ref: str, message: str) -> str:
        """The newest commit reachable from `ref` whose subject holds `message`, or `""`."""
        arguments = [worktree, ref, message]
        found = self._either(
            COMMIT_MATCHING, arguments, arguments, f"find the commit for {message!r}"
        )
        return found.strip()
