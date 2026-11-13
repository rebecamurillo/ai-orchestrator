"""Whether a Run, or a project's Runs, ran on the Claude subscription.

Three-valued: `None` means unknown, and unknown never reads as `False`.
"""

from __future__ import annotations

from collections.abc import Sequence


def run_subscription(flags: Sequence[bool | None]) -> bool | None:
    """`True` if any fact set is true, `False` if there are some and all are false, else `None`."""
    if any(flag is True for flag in flags):
        return True
    if flags and all(flag is False for flag in flags):
        return False
    return None


def group_subscription(flags: Sequence[bool | None]) -> bool | None:
    """The same rule over the Runs of a project."""
    return run_subscription(flags)
