"""The OpenCode session store, read as the fallback when the stream named no session (7.3).

`briefs/7-3-opencode-adapter.md` marks this whole mechanism `[verify]`: the store's path, its
table and its columns are the documented shape and were never observed, and story 7.4 settles
them against the real CLI at `OPENCODE_VERSION`. So the constants are asserted as constants —
one edit each when 7.4 corrects them — and everything else asserted here is the *behaviour*,
which holds whatever the names turn out to be:

- the newest session whose directory is this worktree wins, because a worktree is reused
  across attempts of the same row and the attempt that just ran is the last one written;
- another directory's session is never this attempt's, however new it is;
- **nothing raises.** No file, no table, a column that is not there, a file that is not a
  database at all: each answers "no session", which is exactly what a stream that named none
  already answers. A readiness line failing is a report; an exception here would take the
  walker down for a fallback that is itself optional.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from orchestrator.infrastructure.harness.opencode.sessions import (
    DIRECTORY_COLUMN,
    ID_COLUMN,
    ORDER_COLUMN,
    SESSION_TABLE,
    STORE_RELATIVE_PATH,
    session_for_directory,
    store_path,
)

WORKTREE = Path("/work/acme/widgets/wt/feat-x")
OTHER = Path("/work/acme/widgets/wt/feat-y")
NEWEST = "ses_newest"
OLDEST = "ses_oldest"


def a_store(path: Path, rows: list[tuple[str, str, int]]) -> Path:
    """A store with the documented shape, holding `(id, directory, ordered_at)` rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            f"CREATE TABLE {SESSION_TABLE} "
            f"({ID_COLUMN} TEXT, {DIRECTORY_COLUMN} TEXT, {ORDER_COLUMN} INTEGER)"
        )
        connection.executemany(f"INSERT INTO {SESSION_TABLE} VALUES (?, ?, ?)", rows)
    connection.close()
    return path


# ── where the store lives ────────────────────────────────────────────────────


def test_the_store_hangs_under_the_agents_own_home(tmp_path: Path) -> None:
    """`HOME` is `AGENT_HOME` for every harness process (`env.py::_base_names`), so the
    store the CLI writes is under that home and not under this process's."""
    assert store_path(tmp_path) == tmp_path / STORE_RELATIVE_PATH


def test_the_documented_store_path_is_the_one_the_script_comments_name() -> None:
    assert STORE_RELATIVE_PATH == Path(".local/share/opencode/opencode.db")


# ── the newest session for this worktree ─────────────────────────────────────


def test_the_newest_session_for_the_worktree_wins(tmp_path: Path) -> None:
    store = a_store(
        tmp_path / "db" / "opencode.db", [(OLDEST, str(WORKTREE), 1), (NEWEST, str(WORKTREE), 2)]
    )

    assert session_for_directory(store, WORKTREE) == NEWEST


def test_another_directorys_session_is_never_this_attempts(tmp_path: Path) -> None:
    store = a_store(tmp_path / "db" / "opencode.db", [(NEWEST, str(OTHER), 9)])

    assert session_for_directory(store, WORKTREE) is None


def test_a_store_with_no_rows_for_this_worktree_answers_none(tmp_path: Path) -> None:
    store = a_store(tmp_path / "db" / "opencode.db", [])

    assert session_for_directory(store, WORKTREE) is None


# ── nothing raises ───────────────────────────────────────────────────────────


def test_a_store_that_does_not_exist_answers_none(tmp_path: Path) -> None:
    assert session_for_directory(tmp_path / "nothing" / "opencode.db", WORKTREE) is None


def test_a_store_without_the_documented_table_answers_none(tmp_path: Path) -> None:
    """The `[verify]` case that matters most: 7.4 may find the table is named otherwise, and
    until it does, an adapter that raised here would take the attempt down with it."""
    path = tmp_path / "db" / "opencode.db"
    path.parent.mkdir(parents=True)
    connection = sqlite3.connect(path)
    with connection:
        connection.execute("CREATE TABLE something_else (id TEXT)")
    connection.close()

    assert session_for_directory(path, WORKTREE) is None


def test_a_file_that_is_not_a_database_answers_none(tmp_path: Path) -> None:
    path = tmp_path / "opencode.db"
    path.write_text("not a database")

    assert session_for_directory(path, WORKTREE) is None


def test_the_store_is_opened_read_only(tmp_path: Path) -> None:
    """The store belongs to the harness process, not to this one: a read that could write
    would be a second writer on a file the CLI holds open."""
    store = a_store(tmp_path / "db" / "opencode.db", [(NEWEST, str(WORKTREE), 1)])
    before = store.read_bytes()

    session_for_directory(store, WORKTREE)

    assert store.read_bytes() == before


def test_a_store_path_holding_a_question_mark_still_opens_the_right_file(tmp_path: Path) -> None:
    """The connection is a URI (`mode=ro` travels in it), and a URI truncates at `?`. An
    `AGENT_HOME` holding one would otherwise open — or create — some other file entirely."""
    store = a_store(tmp_path / "why?not" / "opencode.db", [(NEWEST, str(WORKTREE), 1)])

    assert session_for_directory(store, WORKTREE) == NEWEST
