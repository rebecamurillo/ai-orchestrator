"""`RealLogReader`: the last lines of an attempt's log file, read straight off disk.

Plain file I/O, deliberately outside `Workspace` (see `domain/ports/logs.py`'s own
docstring for why). Reading the whole file and slicing its last `n` lines is the simplest
correct implementation for the sizes these logs reach in this release (a single Run's
attempt, not a multi-gigabyte stream); nothing here claims to scale past that.

**Every read is redacted** (AD-5, hard rule 5; defect of 2026-09-20). A harness log is the
one text this system stores that it did not write: `infrastructure/process/runner.py` wires
the child's stdout and stderr straight to the log file descriptor, so whatever a CLI decides
to print is on disk before any code can look at it. OpenCode decides, when it cannot parse
its config, to print that config with `{env:LITELLM_API_KEY}` already resolved — which put a
live Gateway key into a log the API serves in three forms (the paged endpoint, `?download`,
and the Run detail's 40-line tail). Redacting inside this class is what covers all three at
once, because every one of them reads through `tail`, `read_from` or `read_raw`.

It is a mitigation and not a guarantee: a CLI that prints a secret *transformed* — split,
re-encoded, hashed — is not matched by a literal search, and the bytes on disk are never
rewritten. The fix for a leak is still to stop the leak and rotate the credential.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pydantic import SecretStr

from orchestrator.infrastructure.redact import REDACTION, redact
from orchestrator.infrastructure.settings import Settings

_NEWLINE = ord(b"\n")  # 10 — avoids PLR2004 "magic value" in byte comparisons


def log_secrets(settings: Settings) -> tuple[str, ...]:
    """Every credential the instance holds, as the literal strings a log might contain.

    Derived from the `SecretStr` fields themselves rather than from a hand-kept list, so a
    credential added to `Settings` tomorrow is redacted without anyone remembering to come
    back here — the same reason AD-20 makes the settings module the single statement of what
    configuration is. Blank values are dropped: `redact` treats an empty needle as "nothing
    to do", and this keeps that from being load-bearing.

    Deliberately *not* filtered by length. A pathologically short secret would redact
    aggressively and make a log harder to read; failing to redact one would hand it out.
    Those are not equal costs, and this errs at the readable-but-safe end.
    """
    values = []
    for name in type(settings).model_fields:
        value = getattr(settings, name, None)
        if isinstance(value, SecretStr):
            secret = value.get_secret_value()
            if secret:
                values.append(secret)
    return tuple(values)


class RealLogReader:
    """Reads `Attempt.log_path` back for the Run detail's `StepRow.latest.log_tail`.

    `secrets` defaults to empty so a test that reads a fixture log needs no instance
    configuration, and both composition roots (`api/providers.py`, `infrastructure/dbos/
    startup.py`) pass `log_secrets(settings)`. `tests/unit/test_log_redaction.py` asserts
    neither of them constructs a bare reader, because a default that is safe in a test and
    wrong in production has to be held in place by something.
    """

    def __init__(self, secrets: Sequence[str] = ()) -> None:
        self._secrets = tuple(s for s in secrets if s)

    def _scrub(self, text: str) -> str:
        for secret in self._secrets:
            text = redact(text, secret)
        return text

    def _scrub_bytes(self, data: bytes) -> bytes:
        """The same replacement on raw bytes, so `read_raw` never has to decode.

        Decoding to redact and re-encoding would rewrite every byte sequence that is not
        valid UTF-8 — a download is meant to be the file, and only the credentials in it
        should differ.
        """
        for secret in self._secrets:
            data = data.replace(secret.encode("utf-8"), REDACTION.encode("utf-8"))
        return data

    def tail(self, path: str | None, n: int) -> list[str]:
        """The last `n` lines of the file at `path`; `[]` when there is nothing to read.

        `is_file()` and the read are two calls, not one: a log `worktree_gc` (SPEC CAP-11)
        sweeps between them would otherwise turn a routine detail read into a 500 rather
        than the same `[]` a request that arrived a moment later would get.
        """
        if path is None:
            return []
        file = Path(path)
        try:
            if not file.is_file():
                return []
            lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        return [self._scrub(line) for line in lines[-n:]] if n > 0 else []

    def read_from(self, path: str, cursor: int, limit: int) -> tuple[list[str], int, bool] | None:
        """Up to `limit` complete lines from byte `cursor`; `None` on `OSError` (GC'd).

        Opens in binary mode and seeks to `cursor`, so an O(1) seek serves each
        poll regardless of how large the file has grown. Incomplete trailing lines
        (no `\\n` yet) are withheld, keeping the byte cursor deterministic.

        **The cursor counts bytes on disk, and redaction happens after it is computed.**
        `***` is shorter than the credential it replaces, so a cursor derived from the
        redacted text would drift a little further from the file on every page until the
        poll was reading the wrong offsets entirely.
        """
        try:
            with Path(path).open("rb") as f:
                f.seek(cursor)
                chunk = f.read()
        except OSError:
            return None
        total_size = cursor + len(chunk)
        if not chunk:
            return ([], cursor, True)
        last_nl = chunk.rfind(b"\n")
        if last_nl == -1:
            return ([], cursor, False)
        complete = chunk[: last_nl + 1]
        all_lines = complete.decode("utf-8", errors="replace").splitlines()
        if len(all_lines) > limit:
            count = 0
            for i, byte_val in enumerate(complete):
                if byte_val == _NEWLINE:
                    count += 1
                    if count == limit:
                        next_cursor = cursor + i + 1
                        page = [self._scrub(line) for line in all_lines[:limit]]
                        return (page, next_cursor, next_cursor >= total_size)
        next_cursor = cursor + last_nl + 1
        return ([self._scrub(line) for line in all_lines], next_cursor, next_cursor >= total_size)

    def read_raw(self, path: str) -> bytes | None:
        """The full raw content of the file, redacted, or `None` on `OSError` (GC'd)."""
        try:
            return self._scrub_bytes(Path(path).read_bytes())
        except OSError:
            return None
