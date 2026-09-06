"""The `ProtectedPaths` port (AD-17): the frozen-anchor check, as a seam this epic declares.

AD-17's rule — `SPEC.md`, `stories.yaml`, `epics.yaml`, every `AGENTS.md` and every existing
test file are read-only to an agent — is Epic 5's to implement, in
`application/rules/protected_paths.py`, because it needs the story frame's first attempt and
its frozen test set to say anything at all. What Epic 4 needs is the *seam*: `git.commit`
already has the place where a hit turns into `status: error, park: protected_path`, and a
port declared now is what keeps that place from being invented twice.

Nothing implements it in this epic. `StepPorts.protected_paths` is `None`, and `git.commit`
reads that as "no hits" — the honest answer for a system that has not been told what is
protected, and not a silently green check: the Run has no `agent` step yet either (SPEC
non-goals), so there is nothing an agent could have edited.

`check` is a query and returns the hits, never a bool: the Operator reads *which* files were
touched, and a rule that answered yes or no could not tell them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class ProtectedPaths(Protocol):
    """Which of the changed paths this Run is not allowed to commit."""

    def check(self, *, changed: Sequence[str], accepted: Sequence[str]) -> tuple[str, ...]:
        """The protected paths among `changed`, minus the ones the Operator accepted.

        `accepted` is `run.accepted_paths` — what a `continue` on an earlier
        `protected_path` park let through (AD-9) — so a file accepted once is not a hit
        again inside the same story frame.
        """
        ...
