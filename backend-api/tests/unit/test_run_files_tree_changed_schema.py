"""`RunFileEntryChangedOut`/`RunFilesTreeChangedOut.of()` (story 8-3).

Proves the changed-marks schema rules:
- `changed=True` for a file whose `mtime > last_opened_before`
- `changed=False` for a file whose `mtime <= last_opened_before`
- `changed=False` for a directory regardless of mtime
- `changed=False` for every entry when `last_opened_before is None` (first visit)
- Base `RunFileEntryOut` and `RunFilesTreeOut` shapes are NOT modified (frozen tests assert
  their exact `model_dump()` — see `test_run_files_tree_schema.py`)
"""

from __future__ import annotations

from datetime import UTC, datetime

from orchestrator.api.schemas.run_files import RunFileEntryChangedOut, RunFilesTreeChangedOut
from orchestrator.application.use_cases.run_files import RunFilesTree
from orchestrator.domain.ports.workspace import TreeEntry

#: A POSIX timestamp used as the visit cutoff (2026-09-11 10:00:00Z).
CUTOFF = datetime(2026, 9, 11, 10, 0, 0, tzinfo=UTC)
CUTOFF_TS = CUTOFF.timestamp()

#: A file modified one second after the cutoff.
MTIME_AFTER = CUTOFF_TS + 1.0
#: A file modified exactly at the cutoff — not strictly greater, so `changed=False`.
MTIME_AT = CUTOFF_TS
#: A file modified before the cutoff.
MTIME_BEFORE = CUTOFF_TS - 1.0


def test_changed_entry_for_file_newer_than_cutoff() -> None:
    entry = TreeEntry(path="specs/gates/SPEC.md", is_dir=False, size=42, mtime=MTIME_AFTER)
    tree = RunFilesTree(root="specs/gates", entries=(entry,), last_opened_before=CUTOFF)

    out = RunFilesTreeChangedOut.of(tree)

    assert len(out.entries) == 1
    assert out.entries[0].changed is True


def test_not_changed_for_file_at_cutoff() -> None:
    """mtime == cutoff is not strictly greater, so `changed=False`."""
    entry = TreeEntry(path="specs/gates/SPEC.md", is_dir=False, size=42, mtime=MTIME_AT)
    tree = RunFilesTree(root="specs/gates", entries=(entry,), last_opened_before=CUTOFF)

    out = RunFilesTreeChangedOut.of(tree)

    assert out.entries[0].changed is False


def test_not_changed_for_file_older_than_cutoff() -> None:
    entry = TreeEntry(path="specs/gates/SPEC.md", is_dir=False, size=42, mtime=MTIME_BEFORE)
    tree = RunFilesTree(root="specs/gates", entries=(entry,), last_opened_before=CUTOFF)

    out = RunFilesTreeChangedOut.of(tree)

    assert out.entries[0].changed is False


def test_directory_is_never_changed_regardless_of_mtime() -> None:
    """Even if a dir's mtime is after the cutoff, `changed=False` for directories."""
    dir_entry = TreeEntry(path="specs/gates/stories", is_dir=True, mtime=MTIME_AFTER)
    tree = RunFilesTree(root="specs/gates", entries=(dir_entry,), last_opened_before=CUTOFF)

    out = RunFilesTreeChangedOut.of(tree)

    assert out.entries[0].changed is False


def test_all_false_when_last_opened_before_is_none() -> None:
    """`None` cutoff (first visit): every entry is `changed=False`."""
    file_entry = TreeEntry(path="specs/gates/SPEC.md", is_dir=False, size=10, mtime=MTIME_AFTER)
    dir_entry = TreeEntry(path="specs/gates/stories", is_dir=True, mtime=MTIME_AFTER)
    tree = RunFilesTree(
        root="specs/gates",
        entries=(file_entry, dir_entry),
        last_opened_before=None,
    )

    out = RunFilesTreeChangedOut.of(tree)

    assert all(not entry.changed for entry in out.entries)


def test_tree_of_carries_root() -> None:
    tree = RunFilesTree(root="specs/gates", entries=(), last_opened_before=None)

    out = RunFilesTreeChangedOut.of(tree)

    assert out.root == "specs/gates"


def test_changed_entry_model_dump_includes_changed_field() -> None:
    entry = TreeEntry(path="specs/gates/SPEC.md", is_dir=False, size=5, mtime=MTIME_AFTER)
    tree = RunFilesTree(root="specs/gates", entries=(entry,), last_opened_before=CUTOFF)

    out = RunFilesTreeChangedOut.of(tree)

    dumped = out.entries[0].model_dump()
    assert "changed" in dumped
    assert dumped["changed"] is True


def test_unchanged_entry_model_dump_shape() -> None:
    entry = TreeEntry(path="specs/gates/SPEC.md", is_dir=False, size=5, mtime=MTIME_BEFORE)
    tree = RunFilesTree(root="specs/gates", entries=(entry,), last_opened_before=CUTOFF)

    out = RunFilesTreeChangedOut.of(tree)

    dumped = out.entries[0].model_dump()
    assert dumped == {
        "path": "specs/gates/SPEC.md",
        "kind": "file",
        "size": 5,
        "mtime": MTIME_BEFORE,
        "changed": False,
    }


def test_mixed_entries_only_newer_files_are_marked() -> None:
    entries = (
        TreeEntry(path="specs/gates/SPEC.md", is_dir=False, size=1, mtime=MTIME_AFTER),
        TreeEntry(path="specs/gates/stories", is_dir=True, mtime=MTIME_AFTER),
        TreeEntry(path="specs/gates/old.md", is_dir=False, size=1, mtime=MTIME_BEFORE),
    )
    tree = RunFilesTree(root="specs/gates", entries=entries, last_opened_before=CUTOFF)

    out = RunFilesTreeChangedOut.of(tree)

    assert out.entries[0].changed is True  # SPEC.md: newer file
    assert out.entries[1].changed is False  # stories: directory
    assert out.entries[2].changed is False  # old.md: older file


def test_run_file_entry_changed_out_defaults_changed_false() -> None:
    """Direct construction: `changed` defaults to `False`."""
    entry_out = RunFileEntryChangedOut(path="x/y.md", kind="file", size=1, mtime=1.0)
    assert entry_out.changed is False
