"""The OpenCode session store, read when the stream named no session (AD-10, story 7.3).

`briefs/7-3-opencode-adapter.md`: "session id from the JSON events, fallback: the newest
session in `~/.local/share/opencode/opencode.db` whose `directory` equals the worktree
`[verify]`". This module is that fallback, and every name it states is one of the `[verify]`
items — the path, the table, the three columns. Story 7.4 settles them against the real CLI at
`OPENCODE_VERSION`; until it has, none of them is a fact, and the shape of this module is what
makes each of them a one-line edit rather than a rewrite.

**Why read a database the harness owns at all.** OpenCode names its own session and the id is
what the Langfuse plugin keys its trace by, so an attempt with no session id is an attempt
whose generations nobody can find by anything but the Run. The stream is the first place to
look; this is the second, and it exists because a run that was killed, or that buffered its
output, can leave the store written and the log empty.

**Why nothing here ever raises.** Reading it is optional by construction: the primary source
already answered `None`, and the walker is mid-attempt. So a missing file, a table under
another name, a column that is not there, a file that is not a database, a lock held by the CLI
itself — each answers "no session", which is exactly what the stream already answered. The
readiness line reports the absence (7.4); an exception would take the attempt down for a
lookup that was never load-bearing.

**Why read-only.** The store belongs to the harness process. `mode=ro` on the connection URI
is what keeps this process from being a second writer on a file the CLI may still hold open,
and from creating an empty database where the `[verify]` path turns out to be wrong — which
would look exactly like a store with no sessions in it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

#: **Provisional** (addendum §B, 7.4 verifies): where OpenCode keeps its sessions, relative to
#: the harness process's own `HOME` — which `env.py::_base_names` sets to `AGENT_HOME` for every
#: harness. `scripts/harness/opencode.sh`'s invocation comment names the same path, and
#: `tests/unit/test_local_env_contract.py` holds the two statements together.
STORE_RELATIVE_PATH = Path(".local/share/opencode/opencode.db")

#: **Provisional** (addendum §B, 7.4 verifies): the table and the three columns this lookup
#: needs — the session's own id, the directory it was opened in, and the ordering that makes
#: "newest" mean anything.
SESSION_TABLE = "session"
ID_COLUMN = "id"
DIRECTORY_COLUMN = "directory"
ORDER_COLUMN = "time_created"

#: The one row this query wants: the newest session for this worktree.
NEWEST_FOR_DIRECTORY = (
    f"SELECT {ID_COLUMN} FROM {SESSION_TABLE} "
    f"WHERE {DIRECTORY_COLUMN} = ? ORDER BY {ORDER_COLUMN} DESC LIMIT 1"
)

#: Logged (never raised) when the store cannot be read — see the module docstring.
STORE_READ_FAILED = "opencode session store unreadable; the attempt records no session"


def store_path(agent_home: Path) -> Path:
    """Where this instance's OpenCode keeps its sessions.

    Takes the home rather than reading `Settings`, so the one place the path is composed is
    also the one place a test can point somewhere writable.
    """
    return agent_home / STORE_RELATIVE_PATH


def session_for_directory(store: Path, directory: Path) -> str | None:
    """The newest session opened in `directory`, or `None` for every other outcome.

    Newest, because a worktree is reused across attempts of the same row: the session this
    attempt opened is the last one written for that path. That is an approximation and the
    brief marks it one — it is only reached when the run printed no session of its own, and
    the alternative to an approximation here is no session at all.
    """
    if not store.is_file():
        return None
    try:
        # `as_uri()` and not an f-string: the URI form is what carries `mode=ro`, and a path
        # holding a `?` or a `#` would otherwise be truncated at that character and open (or
        # create) some other file entirely. `resolve()` is what lets `as_uri()` be called at
        # all — it requires an absolute path — and the file is known to exist by now.
        connection = sqlite3.connect(f"{store.resolve().as_uri()}?mode=ro", uri=True)
        try:
            row = connection.execute(NEWEST_FOR_DIRECTORY, (str(directory),)).fetchone()
        finally:
            connection.close()
    except sqlite3.Error, OSError, ValueError:
        log.exception(STORE_READ_FAILED, store=str(store), directory=str(directory))
        return None
    if row is None:
        return None
    return row[0] if isinstance(row[0], str) and row[0] else None
