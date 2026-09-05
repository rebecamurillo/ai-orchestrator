"""Replacing a credential with a marker, on every path out of the git adapter (AD-5).

One function, because there is one rule: wherever the token's value appears in text this
process is about to store, log or answer with, it becomes `***`. The adapter calls it on
every `GitError.output` it raises, so a caller that stores the output verbatim — which is
what `run_clone_check` does, because an Operator needs git's own sentence — cannot leak one.

An empty token replaces nothing. `str.replace` with an empty needle inserts the marker
between every character, which would turn an instance with no `GITHUB_TOKEN` into one whose
every git message was unreadable.
"""

from __future__ import annotations

#: What a credential looks like once it has been removed. It says nothing about the value:
#: not its length, not its prefix, not which of the instance's secrets it was.
REDACTION = "***"


def redact(text: str, token: str) -> str:
    """`text` with every occurrence of `token` replaced by `REDACTION`."""
    if not token:
        return text
    return text.replace(token, REDACTION)
