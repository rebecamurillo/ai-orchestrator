"""Reading a harness's own JSON back out of the log it shares with everything else (AD-10).

Every harness this system dispatches prints machine-readable JSON — `claude -p --output-format
stream-json` and `codex exec --json` each print one event per line — and every one
of them prints it into a file that also holds stderr: npm's deprecation warnings, an OTLP
exporter's shutdown errors, a proxy's TLS complaint. So the reading is the same problem twice,
and this module is the one statement of it.

Two properties hold for everything here, and they are why it is worth sharing rather than
copying:

- **Nothing raises.** A log that was never written, a log that is not JSON at all, a JSON array
  where an object was expected, a field that is present but is the string `"n/a"` — each is
  answered with "nothing this system could read", because the alternative is a walker that has
  to catch an exception to learn that a harness printed a warning.
- **Nothing is interpreted.** These functions find objects and coerce numbers. What an object
  *means* — which one is the result, which field is the session, whether a stop was the budget
  cap — belongs to the adapter that knows the harness, and to the use case that knows the rule.

`claude/result.py` re-exports the names it used to define here, so nothing that imported them
from there had to change when `codex/` needed the same four.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

#: The one encoding every log and prompt file is written and read in, so the container's locale
#: never decides what is parsed out of an attempt's own record.
ENCODING = "utf-8"


def read_text(log_path: Path) -> str:
    """The log's text, or nothing at all — a process killed before it wrote has no log."""
    if not log_path.is_file():
        return ""
    return log_path.read_text(encoding=ENCODING, errors="replace")


def json_objects(text: str) -> list[dict[str, Any]]:
    """Every top-level JSON object in `text`, in the order they appear.

    Scanning rather than `json.loads` or a line split: the log holds stdout and stderr
    interleaved, so an object is normally surrounded by whatever the tooling printed and a line
    of a JSON-lines stream can arrive with a warning glued to its front. Each `{` is offered to
    `raw_decode`, and a successful decode advances past the whole object, so a nested one is
    never mistaken for a top-level one.
    """
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    index = text.find("{")
    while index != -1:
        try:
            value, end = decoder.raw_decode(text, index)
        except ValueError:
            index = text.find("{", index + 1)
            continue
        found.append(value)
        index = text.find("{", end)
    return found


def objects_with(
    objects: Iterable[dict[str, Any]], field: str, value: object
) -> list[dict[str, Any]]:
    """The objects whose `field` equals `value`, in order — the harness's own framing, read.

    Selecting on an envelope field is not an interpretation of model output (AD-10): `type` is
    what the harness itself puts on the object it prints, the same class of read as a session
    id. What is inside the selected object is nobody's business here.
    """
    return [item for item in objects if item.get(field) == value]


def as_int(value: Any) -> int | None:
    """A token count, or `None` when the field is there but is not one.

    `bool` is rejected explicitly because it is an `int` in Python, and `True` tokens is a
    reading error rather than one token.
    """
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def as_decimal(value: Any) -> Decimal | None:
    """A USD amount, or `None` when the field is there but is not one."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None
