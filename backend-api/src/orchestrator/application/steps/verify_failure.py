"""Why the `verify` row sent a Story back, as the walker read it (FR-10, AD-9, AD-22)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifyFailure:
    """Why the `verify` row sent this Story back, as the walker read it (FR-10, AD-9).

    A value and not a handle, for the reason every other field of `RunEnvironment` is one:
    the row that failed is a different row, its attempt is a different attempt, and an
    executor that could ask a repository for either would be reading state AD-8 says only
    the walker holds. `walk_context.context` resolves it once, before the executor runs.
    """

    #: The `verify` row's own resolved command, as the Operator would re-run it.
    command: str
    #: What it exited with; `None` when it was sent back before an attempt recorded one.
    exit_code: int | None
    #: The last lines of its log, oldest first, as `LogReader.tail` answered them.
    log_tail: tuple[str, ...] = ()
    #: What the senior made of the failure (AD-22, story 1-6), while the row still owes it
    #: to a fresh dispatch; `""` for every redispatch no senior diagnosed.
    diagnosis: str = ""
