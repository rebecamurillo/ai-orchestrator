"""Replacing a credential with a marker, on every path out of this process (AD-5).

One function, because there is one rule: wherever a secret's value appears in text this
process is about to store, log or answer with, it becomes `***`.

**Two adapters call it, for the same reason and against different text.** The git adapter
redacts every `GitError.output` it raises, so a caller that stores the output verbatim —
which is what `run_clone_check` does, because an Operator needs git's own sentence — cannot
leak one. `infrastructure/process/logs.py` redacts every harness log it reads back, because
a harness CLI's own diagnostics are text this system did not write: OpenCode answers an
unparseable config by printing that config with `{env:LITELLM_API_KEY}` already resolved
(defect of 2026-09-20), and that text reaches the log file before anything can inspect it.
Which is why this module sits beside the adapters rather than inside one of them.

An empty token replaces nothing. `str.replace` with an empty needle inserts the marker
between every character, which would turn an instance with no `GITHUB_TOKEN` into one whose
every git message was unreadable — and, on the log path, every log unreadable.
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
